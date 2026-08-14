"""Tests for LockTimer C3+C4+C5 services — draft, start, materializer, execution, penalties, safety stop."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import domain as d
from app.locktimer import enums as e
from app.locktimer.services.execution import (
    add_slot_rule,
    add_task_rule,
    apply_penalty,
    claim_jobs,
    close_slot,
    complete_task,
    create_draft,
    emit_outbox_event,
    enqueue_job,
    open_slot,
    reveal_task,
    safety_stop,
    skip_task,
    start_session,
    submit_task,
    update_draft,
)
from app.models.locktimer import (
    LockSession,
    LockSlotOccurrence,
    LockTaskOccurrence,
    LockTaskRule,
)
from app.models.user import User
from app.timeutils import as_utc

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# C3 — Draft
# ---------------------------------------------------------------------------


class TestDraft:
    async def test_create_draft(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id, timezone_str="Europe/Moscow")
        assert session.state == e.SESSION_DRAFT
        assert session.owner_id == test_user.id
        assert session.timezone == "Europe/Moscow"
        assert len(session.random_seed_encrypted) == 64
        assert len(session.random_seed_commitment) == 64

    async def test_create_draft_defaults(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        assert session.duration_type == e.DURATION_FROM_START
        assert session.merge_gap_seconds == 3600
        assert not session.can_extend_duration
        assert session.privacy_mode == "private"

    async def test_update_draft_allowed_fields(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await update_draft(
            db_session,
            session,
            can_extend_duration=True,
            merge_gap_seconds=1800,
        )
        assert session.can_extend_duration is True
        assert session.merge_gap_seconds == 1800

    async def test_add_slot_rule(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        rule = await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Morning check",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "09:00"},
            duration_seconds=1800,
        )
        assert rule.session_id == session.id
        assert rule.duration_seconds == 1800
        assert rule.name == "Morning check"

    async def test_add_task_rule(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        rule = await add_task_rule(
            db_session,
            session_id=session.id,
            title="Drink water",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
        )
        assert rule.title == "Drink water"
        assert rule.due_window_seconds == 3600


# ---------------------------------------------------------------------------
# C3 — Start
# ---------------------------------------------------------------------------


class TestStart:
    async def test_start_session_creates_snapshot(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id, timezone_str="UTC")
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Daily",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "09:00"},
            duration_seconds=1800,
        )
        started = await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        assert started.state == e.SESSION_ACTIVE
        assert started.started_at is not None
        assert started.row_version == 1

        # Verify snapshot exists
        from app.models.locktimer import LockSessionSnapshot

        snap = await db_session.execute(select(LockSessionSnapshot).where(LockSessionSnapshot.session_id == session.id))
        snapshot = snap.scalar_one()
        assert snapshot.config_sha256 is not None
        assert len(snapshot.config_sha256) == 64
        canonical = snapshot.canonical_config
        assert "slot_rules" in canonical
        assert len(canonical["slot_rules"]) == 1

    async def test_start_fails_if_already_active(self, db_session: AsyncSession, test_user: User) -> None:
        s1 = await create_draft(db_session, owner_id=test_user.id)
        s1_id = s1.id
        await add_slot_rule(
            db_session,
            session_id=s1_id,
            name="S",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "10:00"},
            duration_seconds=600,
        )
        await start_session(db_session, session_id=s1_id, owner_id=test_user.id, now=FIXED_NOW)

        s2 = await create_draft(db_session, owner_id=test_user.id)
        s2_id = s2.id
        await add_slot_rule(
            db_session,
            session_id=s2_id,
            name="S2",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "10:00"},
            duration_seconds=600,
        )
        with pytest.raises(ValueError, match="active session"):
            await start_session(db_session, session_id=s2_id, owner_id=test_user.id, now=FIXED_NOW)

    async def test_start_creates_occurrences(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Daily slot",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
        )
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="Report",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
        )
        started = await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        assert started.state == e.SESSION_ACTIVE

        # Verify occurrences were materialised
        slots_result = await db_session.execute(
            select(LockSlotOccurrence).where(LockSlotOccurrence.session_id == session.id)
        )
        slots = list(slots_result.scalars().all())
        assert len(slots) > 0, "Expected at least one slot occurrence"

        tasks_result = await db_session.execute(
            select(LockTaskOccurrence).where(LockTaskOccurrence.session_id == session.id)
        )
        tasks = list(tasks_result.scalars().all())
        assert len(tasks) > 0, "Expected at least one task occurrence"


# ---------------------------------------------------------------------------
# C5 — Slots
# ---------------------------------------------------------------------------


class TestSlotExecution:
    async def _started_session_with_slot(
        self, db_session: AsyncSession, test_user: User
    ) -> tuple[LockSession, LockSlotOccurrence]:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Slot",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
            allow_late_open=True,
            extend_on_late_open=True,
            max_late_seconds=3600,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        result = await db_session.execute(select(LockSlotOccurrence).where(LockSlotOccurrence.session_id == session.id))
        occ = result.scalars().first()
        return session, occ

    async def test_open_slot(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await self._started_session_with_slot(db_session, test_user)
        open_time = occ.planned_open_at  # on-time open
        opened = await open_slot(db_session, occurrence=occ, owner_id=test_user.id, now=open_time)
        assert opened.state == e.SLOT_OPEN
        assert as_utc(opened.actual_opened_at) == as_utc(open_time)

    async def test_open_slot_idempotent(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await self._started_session_with_slot(db_session, test_user)
        open_time = occ.planned_open_at
        await open_slot(db_session, occurrence=occ, owner_id=test_user.id, now=open_time)
        with pytest.raises(ValueError):
            await open_slot(db_session, occurrence=occ, owner_id=test_user.id, now=open_time)

    async def test_open_slot_with_aware_now(self, db_session: AsyncSession, test_user: User) -> None:
        """Aware `now` vs a SQLite-read (naive) occurrence must not raise (tz regression)."""
        _, occ = await self._started_session_with_slot(db_session, test_user)
        aware_now = as_utc(occ.planned_open_at)
        opened = await open_slot(db_session, occurrence=occ, owner_id=test_user.id, now=aware_now)
        assert opened.state == e.SLOT_OPEN

    async def test_close_slot(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await self._started_session_with_slot(db_session, test_user)
        opened = await open_slot(db_session, occurrence=occ, owner_id=test_user.id, now=occ.planned_open_at)
        closed = await close_slot(db_session, occurrence=opened, owner_id=test_user.id)
        assert closed.state == e.SLOT_CLOSED

    async def test_late_open_applies_extension(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await self._started_session_with_slot(db_session, test_user)
        late_time = occ.planned_open_at + timedelta(seconds=1800)  # 30 min late
        opened = await open_slot(db_session, occurrence=occ, owner_id=test_user.id, now=late_time)
        assert opened.extension_applied_seconds > 0


# ---------------------------------------------------------------------------
# C5 — Tasks
# ---------------------------------------------------------------------------


class TestTaskExecution:
    async def _started_session_with_task(
        self, db_session: AsyncSession, test_user: User
    ) -> tuple[LockSession, LockTaskOccurrence]:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="Report",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
            requires_report=True,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        result = await db_session.execute(select(LockTaskOccurrence).where(LockTaskOccurrence.session_id == session.id))
        occ = result.scalars().first()
        return session, occ

    async def test_reveal_task(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await self._started_session_with_task(db_session, test_user)
        revealed = await reveal_task(db_session, occurrence=occ, owner_id=test_user.id)
        assert revealed.content_visible is True

    async def test_submit_and_complete_task(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await self._started_session_with_task(db_session, test_user)
        await reveal_task(db_session, occurrence=occ, owner_id=test_user.id)
        submitted = await submit_task(db_session, occurrence=occ, owner_id=test_user.id)
        assert submitted.state == e.TASK_SUBMITTED
        completed = await complete_task(db_session, occurrence=submitted, owner_id=test_user.id)
        assert completed.state == e.TASK_COMPLETED
        assert completed.finalized_at is not None

    async def test_skip_task(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await self._started_session_with_task(db_session, test_user)
        skipped = await skip_task(db_session, occurrence=occ, owner_id=test_user.id)
        assert skipped.state == e.TASK_SKIPPED

    async def test_complete_idempotent(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await self._started_session_with_task(db_session, test_user)
        await reveal_task(db_session, occurrence=occ, owner_id=test_user.id)
        submitted = await submit_task(db_session, occurrence=occ, owner_id=test_user.id)
        await complete_task(db_session, occurrence=submitted, owner_id=test_user.id)
        with pytest.raises(ValueError):
            await complete_task(db_session, occurrence=submitted, owner_id=test_user.id)


# ---------------------------------------------------------------------------
# C5 — Penalties
# ---------------------------------------------------------------------------


class TestPenalties:
    async def test_apply_penalty(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="S",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)

        event = await apply_penalty(
            db_session,
            session_id=session.id,
            penalty_type=e.PENALTY_BLOCK_NEXT_SLOT,
            source_kind="slot_occurrence",
            source_id=uuid.uuid4(),
            reason_code="late_close",
            idempotency_key="test-key-1",
        )
        assert event is not None
        assert event.state == e.PENALTY_APPLIED
        assert event.penalty_type == e.PENALTY_BLOCK_NEXT_SLOT

    async def test_penalty_idempotent(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="S",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)

        e1 = await apply_penalty(
            db_session,
            session_id=session.id,
            penalty_type=e.PENALTY_POINTS,
            source_kind="task",
            source_id=uuid.uuid4(),
            requested_value=10,
            idempotency_key="dup-key",
        )
        e2 = await apply_penalty(
            db_session,
            session_id=session.id,
            penalty_type=e.PENALTY_POINTS,
            source_kind="task",
            source_id=uuid.uuid4(),
            requested_value=10,
            idempotency_key="dup-key",
        )
        assert e1 is not None
        assert e2 is None  # idempotent

    async def test_unknown_penalty_type_raises(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="S",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00"},
            duration_seconds=1800,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        with pytest.raises(ValueError, match="Unknown penalty type"):
            await apply_penalty(
                db_session,
                session_id=session.id,
                penalty_type="invalid_type",
                source_kind="task",
                source_id=uuid.uuid4(),
            )


# ---------------------------------------------------------------------------
# C5 — Safety Stop
# ---------------------------------------------------------------------------


class TestSafetyStop:
    async def test_safety_stop_cancels_future(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="S",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
        )
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="T",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)

        stopped = await safety_stop(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        assert stopped.state == e.SESSION_SAFETY_STOPPED
        assert stopped.safety_stopped_at is not None
        assert stopped.safety_stop_reason_code == "user_requested"

    async def test_safety_stop_only_active(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        with pytest.raises(ValueError, match="state"):
            await safety_stop(db_session, session_id=session.id, owner_id=test_user.id)

    async def test_invalid_safety_stop_reason(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="S",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00"},
            duration_seconds=1800,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        with pytest.raises(ValueError, match="Invalid safety stop reason"):
            await safety_stop(db_session, session_id=session.id, owner_id=test_user.id, reason_code="bad_reason")


# ---------------------------------------------------------------------------
# C5 — Outbox
# ---------------------------------------------------------------------------


class TestOutbox:
    async def test_emit_outbox_event(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        event = await emit_outbox_event(
            db_session,
            aggregate_type="lock_session",
            aggregate_id=session.id,
            event_type="locktimer.session.started",
            payload={"key": "value"},
        )
        assert event.aggregate_type == "lock_session"
        assert event.state == "pending"
        assert event.payload == {"key": "value"}


# ---------------------------------------------------------------------------
# C4 — Job runner
# ---------------------------------------------------------------------------


class TestJobRunner:
    async def test_enqueue_job(self, db_session: AsyncSession, test_user: User) -> None:
        job = await enqueue_job(
            db_session,
            job_key="test-job-1",
            job_type="materialize",
            payload={"session_id": str(uuid.uuid4())},
        )
        assert job.state == "pending"
        assert job.job_key == "test-job-1"

    async def test_enqueue_job_idempotent(self, db_session: AsyncSession, test_user: User) -> None:
        j1 = await enqueue_job(db_session, job_key="dup-job", job_type="test")
        j2 = await enqueue_job(db_session, job_key="dup-job", job_type="test")
        assert j1.id == j2.id

    async def test_claim_jobs(self, db_session: AsyncSession, test_user: User) -> None:
        await enqueue_job(db_session, job_key="j1", job_type="materialize")
        await enqueue_job(db_session, job_key="j2", job_type="materialize")
        await enqueue_job(db_session, job_key="j3", job_type="other")

        claimed = await claim_jobs(db_session, worker_id="worker-1", job_types=["materialize"], limit=5)
        assert len(claimed) == 2
        for job in claimed:
            assert job.state == "running"
            assert job.lease_owner == "worker-1"


# ---------------------------------------------------------------------------
# C4 — Materializer (deterministic)
# ---------------------------------------------------------------------------


class TestMaterializerScheduleTypes:
    async def test_every_n_days_generates_correct_count(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Every 2 days",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 2, "time_of_day": "09:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)

        result = await db_session.execute(select(LockSlotOccurrence).where(LockSlotOccurrence.session_id == session.id))
        occs = list(result.scalars().all())
        # 90 days / 2 = 45 occurrences
        assert 40 <= len(occs) <= 50, f"Expected ~45, got {len(occs)}"

    async def test_daily_task_generates_occurrences(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="Daily check",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "08:00"},
            due_window_seconds=3600,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)

        result = await db_session.execute(select(LockTaskOccurrence).where(LockTaskOccurrence.session_id == session.id))
        tasks = list(result.scalars().all())
        assert 85 <= len(tasks) <= 95, f"Expected ~90, got {len(tasks)}"

    async def test_deterministic_random_is_reproducible(self, db_session: AsyncSession, test_user: User) -> None:
        """Same seed + same rules → same occurrences."""
        seed = d.generate_random_seed()
        session1 = LockSession(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            state=e.SESSION_ACTIVE,
            duration_type=e.DURATION_FROM_START,
            timezone="UTC",
            merge_gap_seconds=3600,
            can_extend_duration=False,
            random_seed_encrypted=seed,
            random_seed_commitment=d.compute_seed_commitment(seed),
            privacy_mode="private",
            row_version=1,
        )
        session2 = LockSession(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            state=e.SESSION_ACTIVE,
            duration_type=e.DURATION_FROM_START,
            timezone="UTC",
            merge_gap_seconds=3600,
            can_extend_duration=False,
            random_seed_encrypted=seed,
            random_seed_commitment=d.compute_seed_commitment(seed),
            privacy_mode="private",
            row_version=1,
        )

        rule1 = LockTaskRule(
            id=uuid.uuid4(),
            session_id=session1.id,
            client_key=uuid.uuid4(),
            title="Random task",
            schedule_type=e.TASK_SCHED_DETERMINISTIC_RANDOM,
            schedule={"count": 3},
            due_window_seconds=3600,
            schema_version=1,
        )
        rule2 = LockTaskRule(
            id=rule1.id,
            session_id=session2.id,
            client_key=uuid.uuid4(),
            title="Random task",
            schedule_type=e.TASK_SCHED_DETERMINISTIC_RANDOM,
            schedule={"count": 3},
            due_window_seconds=3600,
            schema_version=1,
        )

        from app.locktimer.services.execution import _generate_task_occurrences

        occs1 = _generate_task_occurrences(session1, rule1, FIXED_NOW, FIXED_NOW + timedelta(days=7))
        occs2 = _generate_task_occurrences(session2, rule2, FIXED_NOW, FIXED_NOW + timedelta(days=7))

        assert len(occs1) == len(occs2) == 3
        for o1, o2 in zip(occs1, occs2, strict=True):
            assert o1.appears_at == o2.appears_at
            assert o1.due_at == o2.due_at


# ---------------------------------------------------------------------------
# Date-range queries — regression: timestamptz vs VARCHAR (PostgreSQL) +
# local-day bucketing in the client timezone.
# ---------------------------------------------------------------------------


class TestDateRangeQueries:
    async def _make_session(
        self,
        db_session: AsyncSession,
        test_user: User,
        started_at: datetime,
        effective_end_at: datetime,
    ) -> LockSession:
        seed = d.generate_random_seed()
        session = LockSession(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            state=e.SESSION_COMPLETED,
            duration_type=e.DURATION_FROM_START,
            timezone="UTC",
            merge_gap_seconds=3600,
            can_extend_duration=False,
            random_seed_encrypted=seed,
            random_seed_commitment=d.compute_seed_commitment(seed),
            privacy_mode="private",
            row_version=1,
            started_at=started_at,
            effective_end_at=effective_end_at,
        )
        db_session.add(session)
        await db_session.flush()
        return session

    async def test_overlap_semantics(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.repositories import list_sessions_by_date_range

        inside = await self._make_session(
            db_session,
            test_user,
            datetime(2026, 8, 6, 10, 0, tzinfo=UTC),
            datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
        )
        straddles = await self._make_session(
            db_session,
            test_user,
            datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
            datetime(2026, 8, 6, 2, 0, tzinfo=UTC),
        )
        outside = await self._make_session(
            db_session,
            test_user,
            datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
            datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        )

        found = await list_sessions_by_date_range(db_session, test_user.id, "2026-08-06", "2026-08-06")
        ids = {s.id for s in found}
        assert inside.id in ids
        assert straddles.id in ids
        assert outside.id not in ids

    async def test_wide_range_includes_all(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.repositories import list_sessions_by_date_range

        s1 = await self._make_session(
            db_session,
            test_user,
            datetime(2026, 8, 3, 8, 0, tzinfo=UTC),
            datetime(2026, 8, 3, 9, 0, tzinfo=UTC),
        )
        s2 = await self._make_session(
            db_session,
            test_user,
            datetime(2026, 8, 20, 18, 0, tzinfo=UTC),
            datetime(2026, 8, 20, 19, 0, tzinfo=UTC),
        )

        found = await list_sessions_by_date_range(db_session, test_user.id, "2026-08-01", "2026-08-31")
        ids = {s.id for s in found}
        assert s1.id in ids
        assert s2.id in ids

    async def test_client_tz_day_bucketing(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.repositories import list_sessions_by_date_range
        from app.timeutils import reset_client_tz, set_client_tz

        # 2026-08-05 16:30 UTC == 2026-08-06 01:30 in Asia/Tokyo (UTC+9).
        session = await self._make_session(
            db_session,
            test_user,
            datetime(2026, 8, 5, 16, 30, tzinfo=UTC),
            datetime(2026, 8, 5, 20, 0, tzinfo=UTC),
        )

        # No client tz (UTC fallback): the session is on 08-05 → excluded from 08-06.
        found_utc = await list_sessions_by_date_range(db_session, test_user.id, "2026-08-06", "2026-08-06")
        assert session.id not in {s.id for s in found_utc}

        # Tokyo cookie: the session is on 08-06 → included.
        token = set_client_tz("Asia/Tokyo")
        try:
            found_tokyo = await list_sessions_by_date_range(db_session, test_user.id, "2026-08-06", "2026-08-06")
        finally:
            reset_client_tz(token)
        assert session.id in {s.id for s in found_tokyo}


# ---------------------------------------------------------------------------
# Q14 — penalties wired into skip / late close (Session 120)
# ---------------------------------------------------------------------------


class TestQ14PenaltyWiring:
    async def test_skip_applies_rule_penalty_policy(self, db_session: AsyncSession, test_user: User) -> None:
        """Skipping a task whose rule has penalty_policy applies the penalty."""
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="Penalised report",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
            penalty_policy={"type": e.PENALTY_POINTS, "value": 5},
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        result = await db_session.execute(select(LockTaskOccurrence).where(LockTaskOccurrence.session_id == session.id))
        occ = result.scalars().first()

        await skip_task(db_session, occurrence=occ, owner_id=test_user.id)

        from app.locktimer.services.execution import get_penalty_for_source

        penalty = await get_penalty_for_source(
            db_session,
            source_kind="task_occurrence",
            source_id=occ.id,
        )
        assert penalty is not None
        assert penalty.penalty_type == e.PENALTY_POINTS
        assert penalty.requested_value == 5
        assert penalty.state == e.PENALTY_APPLIED

    async def test_skip_without_policy_no_penalty(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="No penalty",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        result = await db_session.execute(select(LockTaskOccurrence).where(LockTaskOccurrence.session_id == session.id))
        occ = result.scalars().first()

        await skip_task(db_session, occurrence=occ, owner_id=test_user.id)

        from app.locktimer.services.execution import get_penalty_for_source

        assert (await get_penalty_for_source(db_session, source_kind="task_occurrence", source_id=occ.id)) is None

    async def test_skip_penalty_idempotent_per_occurrence(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="Idempotent",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
            penalty_policy={"type": e.PENALTY_POINTS, "value": 5},
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        result = await db_session.execute(select(LockTaskOccurrence).where(LockTaskOccurrence.session_id == session.id))
        occ = result.scalars().first()

        await skip_task(db_session, occurrence=occ, owner_id=test_user.id)
        with pytest.raises(ValueError):
            await skip_task(db_session, occurrence=occ, owner_id=test_user.id)

        from app.locktimer.services.execution import get_penalty_for_source

        penalty = await get_penalty_for_source(db_session, source_kind="task_occurrence", source_id=occ.id)
        assert penalty is not None  # exactly one event (idempotency key skip:{id})

    async def test_late_close_applies_late_close_policy(self, db_session: AsyncSession, test_user: User) -> None:
        """Closing a slot after close_due_at applies the rule's late_close_policy."""
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Late window",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
            late_close_policy={"type": e.PENALTY_ADD_TIME, "value": 600},
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        result = await db_session.execute(select(LockSlotOccurrence).where(LockSlotOccurrence.session_id == session.id))
        occ = result.scalars().first()

        opened = await open_slot(db_session, occurrence=occ, owner_id=test_user.id, now=occ.planned_open_at)
        # Close well after close_due_at.
        late_close = as_utc(opened.close_due_at) + timedelta(seconds=900)
        closed = await close_slot(db_session, occurrence=opened, owner_id=test_user.id, now=late_close)
        assert closed.state == e.SLOT_CLOSED

        from app.locktimer.services.execution import get_penalty_for_source

        penalty = await get_penalty_for_source(
            db_session,
            source_kind="slot_occurrence",
            source_id=opened.id,
        )
        assert penalty is not None
        assert penalty.penalty_type == e.PENALTY_ADD_TIME
        assert penalty.requested_value == 600

    async def test_on_time_close_no_penalty(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="On time",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
            late_close_policy={"type": e.PENALTY_ADD_TIME, "value": 600},
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        result = await db_session.execute(select(LockSlotOccurrence).where(LockSlotOccurrence.session_id == session.id))
        occ = result.scalars().first()

        opened = await open_slot(db_session, occurrence=occ, owner_id=test_user.id, now=occ.planned_open_at)
        # Close within due time.
        await close_slot(db_session, occurrence=opened, owner_id=test_user.id, now=opened.close_due_at)

        from app.locktimer.services.execution import get_penalty_for_source

        assert (await get_penalty_for_source(db_session, source_kind="slot_occurrence", source_id=opened.id)) is None

    async def test_unknown_policy_type_no_crash(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="Bad policy",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
            penalty_policy={"type": "unknown_kind", "value": 5},
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        result = await db_session.execute(select(LockTaskOccurrence).where(LockTaskOccurrence.session_id == session.id))
        occ = result.scalars().first()

        # Must not raise — just skip the malformed policy.
        skipped = await skip_task(db_session, occurrence=occ, owner_id=test_user.id)
        assert skipped.state == e.TASK_SKIPPED
