"""Шаг 12 tests — medicine in game content + task lists (ADR-085).

Covers:
- LockTimer relief-task: med schedule → task rule with penalty disabled
- LockTimer relief-task API endpoint
- Dashboard 'today' merge: due meds appear in today_items (view-level)
- Inventory→medicine one-time migration (idempotent, provenance)
- Adherence streak helper
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer.services.execution import (
    add_medication_task_rule,
    create_draft,
    get_penalty_for_source,
    skip_task,
    start_session,
)
from app.models.life import InventoryItem
from app.models.locktimer import LockTaskOccurrence, LockTaskRule
from app.models.medication import Medication, MedSchedule
from app.models.user import User

pytestmark = pytest.mark.anyio

FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


async def _make_med_schedule(db: AsyncSession, user: User, name: str = "Vitamin D") -> MedSchedule:
    med = Medication(user_id=user.id, name=name, kind="medication", unit="capsule")
    db.add(med)
    await db.flush()
    sched = MedSchedule(
        user_id=user.id,
        medication_id=med.id,
        dose_quantity=1.0,
        dose_unit="capsule",
        frequency_type="daily",
        times_of_day=["09:00"],
        is_active=True,
    )
    db.add(sched)
    await db.flush()
    return sched


# ─────────────────────────────────────────────────────────────────────────────
# LockTimer relief-task (ADR-085)
# ─────────────────────────────────────────────────────────────────────────────


class TestReliefTask:
    async def test_relief_task_created_without_penalty_policy(self, db_session: AsyncSession, test_user: User) -> None:
        sched = await _make_med_schedule(db_session, test_user, "Ibuprofen")
        session = await create_draft(db_session, owner_id=test_user.id)
        rule = await add_medication_task_rule(
            db_session,
            session_id=session.id,
            med_schedule_id=sched.id,
            owner_id=test_user.id,
        )
        assert rule.title == "Ibuprofen (1 capsule)"
        assert rule.category == "medication"
        assert rule.penalty_policy is None  # relief-only — never penalizes
        assert rule.availability_policy.get("relief") == "medication"
        assert rule.llm_flags.get("relief") == "medication"

    async def test_relief_task_skip_has_no_penalty(self, db_session: AsyncSession, test_user: User) -> None:
        sched = await _make_med_schedule(db_session, test_user, "Vitamin D")
        session = await create_draft(db_session, owner_id=test_user.id)
        rule = await add_medication_task_rule(
            db_session,
            session_id=session.id,
            med_schedule_id=sched.id,
            owner_id=test_user.id,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        result = await db_session.execute(select(LockTaskOccurrence).where(LockTaskOccurrence.rule_id == rule.id))
        occ = result.scalars().first()
        assert occ is not None
        await skip_task(db_session, occurrence=occ, owner_id=test_user.id)
        penalty = await get_penalty_for_source(db_session, source_kind="task_occurrence", source_id=occ.id)
        assert penalty is None  # relief task skip → no penalty

    async def test_relief_task_unknown_schedule_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        with pytest.raises(ValueError, match="schedule not found"):
            await add_medication_task_rule(
                db_session,
                session_id=session.id,
                med_schedule_id=uuid.uuid4(),
                owner_id=test_user.id,
            )

    async def test_relief_task_api_creates_rule(self, db_session, auth_client, test_user: User) -> None:
        sched = await _make_med_schedule(db_session, test_user, "Magnesium")
        session = await create_draft(db_session, owner_id=test_user.id)
        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/medication-task-rules",
            data={"med_schedule_id": str(sched.id)},
            follow_redirects=False,
        )
        assert resp.status_code in (303, 302)
        result = await db_session.execute(select(LockTaskRule).where(LockTaskRule.session_id == session.id))
        rules = list(result.scalars().all())
        assert len(rules) == 1
        assert rules[0].title == "Magnesium (1 capsule)"
        assert rules[0].penalty_policy is None

    async def test_relief_task_api_rejects_active_session(self, db_session, auth_client, test_user: User) -> None:
        sched = await _make_med_schedule(db_session, test_user, "Zinc")
        session = await create_draft(db_session, owner_id=test_user.id)
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/medication-task-rules",
            data={"med_schedule_id": str(sched.id)},
            follow_redirects=False,
        )
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard 'today' merge (view-level)
# ─────────────────────────────────────────────────────────────────────────────


class TestDashboardTodayMerge:
    async def test_today_items_include_due_meds(self, db_session, auth_client, test_user: User) -> None:
        await _make_med_schedule(db_session, test_user, "Melatonin")
        resp = await auth_client.get("/dashboard")
        assert resp.status_code == 200
        html = resp.text
        # The today block renders the med with a medication icon link.
        assert "Melatonin" in html
        assert "dash-block-today" in html

    async def test_today_items_without_meds_no_crash(self, db_session, auth_client, test_user: User) -> None:
        resp = await auth_client.get("/dashboard")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Inventory → medicine migration (one-time, idempotent)
# ─────────────────────────────────────────────────────────────────────────────


class TestInventoryMigration:
    async def test_migrate_medical_inventory_items(self, db_session, auth_client, test_user: User) -> None:
        medical = InventoryItem(
            user_id=test_user.id,
            category="hygiene_supply",
            name="Iodine solution",
            description="Antiseptic 10%",
            quantity=1,
        )
        non_medical = InventoryItem(
            user_id=test_user.id,
            category="clothing",
            name="Black stockings",
            quantity=1,
        )
        db_session.add_all([medical, non_medical])
        await db_session.flush()

        resp = await auth_client.post("/medications/migrate-inventory", follow_redirects=False)
        assert resp.status_code == 303
        assert "migrated=1" in resp.headers.get("location", "")

        meds = (await db_session.execute(select(Medication).where(Medication.user_id == test_user.id))).scalars().all()
        assert len(meds) == 1
        assert meds[0].name == "Iodine solution"
        assert meds[0].source_inventory_id == medical.id

        # migrated item is marked (not deleted)
        fresh = await db_session.get(InventoryItem, medical.id)
        assert fresh.migrated_to_medication is True
        non = await db_session.get(InventoryItem, non_medical.id)
        assert non.migrated_to_medication is False

    async def test_migration_idempotent(self, db_session, auth_client, test_user: User) -> None:
        medical = InventoryItem(
            user_id=test_user.id,
            category="consumable",
            name="Bandage roll",
            quantity=1,
        )
        db_session.add(medical)
        await db_session.flush()

        await auth_client.post("/medications/migrate-inventory", follow_redirects=False)
        resp2 = await auth_client.post("/medications/migrate-inventory", follow_redirects=False)
        assert "migrated=0" in resp2.headers.get("location", "")

        meds = (await db_session.execute(select(Medication).where(Medication.user_id == test_user.id))).scalars().all()
        assert len(meds) == 1  # no duplicate

    async def test_migration_skips_duplicate_name(self, db_session, auth_client, test_user: User) -> None:
        await _make_med_schedule(db_session, test_user, "Paracetamol")
        # Same name in inventory → skipped as duplicate
        item = InventoryItem(user_id=test_user.id, category="other", name="Paracetamol", quantity=1)
        db_session.add(item)
        await db_session.flush()

        resp = await auth_client.post("/medications/migrate-inventory", follow_redirects=False)
        assert "skipped=1" in resp.headers.get("location", "")

    async def test_migrated_items_hidden_from_inventory(self, db_session, auth_client, test_user: User) -> None:
        medical = InventoryItem(
            user_id=test_user.id,
            category="hygiene_supply",
            name="Hydrogen peroxide",
            quantity=1,
            migrated_to_medication=True,
        )
        db_session.add(medical)
        await db_session.flush()

        resp = await auth_client.get("/api/v2/inventory")
        assert resp.status_code == 200
        assert all(item["name"] != "Hydrogen peroxide" for item in resp.json())


# ─────────────────────────────────────────────────────────────────────────────
# Adherence streak helper
# ─────────────────────────────────────────────────────────────────────────────


class TestAdherenceStreak:
    async def test_streak_zero_without_intakes(self, db_session, test_user: User) -> None:
        from app.gamification.medication import adherence_streak

        await _make_med_schedule(db_session, test_user, "Vitamin D")
        streak = await adherence_streak(db_session, test_user.id)
        assert streak == 0


# ─────────────────────────────────────────────────────────────────────────────
# ADR-137 — configurable medication gamification (positive-only)
# ─────────────────────────────────────────────────────────────────────────────


class TestMedicationGamificationToggle:
    """ADR-137: prefs.med_gamification gates adherence XP/achievements.

    Default is ON (legacy behavior preserved). When OFF, an on-time intake is
    still recorded but awards no XP and no achievements.
    """

    async def test_default_prefs_gamification_enabled(self, db_session, test_user: User) -> None:
        from app.prefs import prefs_from_dict

        prefs = prefs_from_dict(test_user.prefs)
        assert prefs.med_gamification is True

    async def test_prefs_gamification_disabled_awards_no_xp(
        self, db_session, test_user: User, auth_client
    ) -> None:
        from app.gamification.medication import on_medication_taken
        from app.models.medication import MedIntake, MedSchedule
        from app.prefs import raw_dict, sanitize_prefs

        # Turn gamification off via prefs (as /settings would persist).
        raw = sanitize_prefs(raw_dict(test_user.prefs))
        raw["med_gamification"] = False
        test_user.prefs = raw
        await db_session.flush()

        med = Medication(user_id=test_user.id, name="Vitamin D", kind="supplement")
        db_session.add(med)
        await db_session.flush()
        sched = MedSchedule(
            user_id=test_user.id,
            medication_id=med.id,
            dose_quantity=1,
            dose_unit="tab",
            frequency_type="daily",
            times_per_day=1,
        )
        db_session.add(sched)
        await db_session.flush()

        db_session.add(
            MedIntake(
                user_id=test_user.id,
                medication_id=med.id,
                schedule_id=sched.id,
                scheduled_at=datetime.now(UTC),
                taken_at=datetime.now(UTC),
                status="taken",
                quantity_taken=1,
            )
        )
        await db_session.flush()

        result = await on_medication_taken(db_session, test_user.id, med.name, on_time=True)
        await db_session.commit()

        # Intake recorded, but no gamification side effects.
        assert result["xp_earned"] == 0
        assert result["new_achievements"] == 0
        intakes = (await db_session.execute(select(MedIntake).where(MedIntake.user_id == test_user.id))).scalars().all()
        assert len(intakes) == 1
        assert intakes[0].status == "taken"

    async def test_prefs_gamification_enabled_awards_xp(
        self, db_session, test_user: User
    ) -> None:
        from app.gamification.medication import on_medication_taken
        from app.models.medication import MedIntake, MedSchedule

        med = Medication(user_id=test_user.id, name="Vitamin D", kind="supplement")
        db_session.add(med)
        await db_session.flush()
        sched = MedSchedule(
            user_id=test_user.id,
            medication_id=med.id,
            dose_quantity=1,
            dose_unit="tab",
            frequency_type="daily",
            times_per_day=1,
        )
        db_session.add(sched)
        await db_session.flush()

        db_session.add(
            MedIntake(
                user_id=test_user.id,
                medication_id=med.id,
                schedule_id=sched.id,
                scheduled_at=datetime.now(UTC),
                taken_at=datetime.now(UTC),
                status="taken",
                quantity_taken=1,
            )
        )
        await db_session.flush()

        result = await on_medication_taken(db_session, test_user.id, med.name, on_time=True)
        await db_session.commit()
        assert result["xp_earned"] > 0
