"""Phase 1 (Session 58) tests — new activity model infrastructure.

Covers ADR-035 (ActivityCategory + seed), ADR-036 (ActivityLog→ActivityTask
columns), ADR-037 (session planned times / accepted_at), ADR-038
(penalty_enabled), ADR-040 (status machine + audit journal).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.category import ActivityCategory
from app.models.entity import Entity
from app.models.session import ActivitySession
from app.models.task_history import ActivityTaskHistory
from app.models.task_status import (
    CANCELLED,
    COMPLETED,
    DRAFT,
    IN_PROGRESS,
    PLANNED,
    REVIEW_NEEDED,
    SKIPPED,
    STATUS_TRANSITIONS,
    STOPPED,
    TASK_STATUSES,
    can_transition,
    is_valid_status,
    normalize_status,
)
from app.seed_categories import SEED_CATEGORIES, seed_categories

# ── ADR-035: ActivityCategory + seed ────────────────────────────────────


@pytest.mark.asyncio
async def test_seed_categories_creates_16_toplevel(db_session):
    """16 top-level categories with nested subcategories are seeded once."""
    created = await seed_categories(db_session)
    await db_session.flush()

    result = await db_session.execute(select(ActivityCategory))
    cats = result.scalars().all()

    assert len(cats) == len(created) > 16
    toplevel = [c for c in cats if c.parent_id is None]
    assert len(toplevel) == 16
    assert {c.slug for c in toplevel} == {slug for slug, *_ in SEED_CATEGORIES}


@pytest.mark.asyncio
async def test_seed_categories_is_idempotent(db_session):
    """Second call does not duplicate categories."""
    await seed_categories(db_session)
    await db_session.flush()
    await seed_categories(db_session)
    await db_session.flush()

    result = await db_session.execute(select(ActivityCategory))
    assert len(result.scalars().all()) == len(SEED_CATEGORIES) + sum(
        len(children) for _, _, _, children in SEED_CATEGORIES
    )


@pytest.mark.asyncio
async def test_entity_category_fk(db_session, test_user):
    """Entity can link to an ActivityCategory (category_rel)."""
    cat = ActivityCategory(slug="test_cat", title="Test Category", sort_order=1)
    db_session.add(cat)
    await db_session.flush()

    entity = Entity(
        real_name="Test Activity",
        slug="test-activity",
        category="Test Category",
        category_id=cat.id,
        owner_id=test_user.id,
    )
    db_session.add(entity)
    await db_session.flush()

    assert entity.category_rel is not None
    assert entity.category_rel.slug == "test_cat"


# ── ADR-040: status machine ─────────────────────────────────────────────


def test_status_enum_has_11_states():
    assert len(TASK_STATUSES) == 11
    for s in (DRAFT, PLANNED, IN_PROGRESS, COMPLETED, SKIPPED, CANCELLED, STOPPED, REVIEW_NEEDED):
        assert is_valid_status(s)


def test_normalize_status_maps_legacy():
    assert normalize_status("pending") == PLANNED
    assert normalize_status("interrupted") == STOPPED
    assert normalize_status("completed") == COMPLETED
    assert normalize_status(None) == PLANNED
    assert normalize_status("planned") == PLANNED


def test_legal_transitions():
    assert can_transition(PLANNED, COMPLETED)
    assert can_transition(PLANNED, IN_PROGRESS)
    assert can_transition(PLANNED, SKIPPED)
    assert can_transition(PLANNED, CANCELLED)
    assert can_transition(IN_PROGRESS, STOPPED)
    assert can_transition(STOPPED, IN_PROGRESS)  # resume allowed
    assert can_transition(COMPLETED, REVIEW_NEEDED)


def test_illegal_transitions():
    # Cannot go straight from draft to completed; cannot complete a cancelled task
    assert not can_transition(DRAFT, COMPLETED)
    assert not can_transition(CANCELLED, COMPLETED)
    assert not can_transition(COMPLETED, STOPPED)
    assert not can_transition(SKIPPED, COMPLETED)
    # Every status has at least one outgoing transition defined
    for s in TASK_STATUSES:
        assert s in STATUS_TRANSITIONS


# ── ADR-036: ActivityLog → ActivityTask columns ─────────────────────────


@pytest.mark.asyncio
async def test_activity_log_evolution_columns(db_session, test_user):
    """New task columns persist: title_override, scheduled_at, comments, actual params."""
    log = ActivityLog(
        user_id=test_user.id,
        status="planned",
        title_override="My custom title",
        scheduled_at=datetime.now(UTC) + timedelta(hours=3),
        planned_comment="Plan note",
        completion_comment="Done note",
        actual_parameters={"count": 10, "intensity": 3},
        selected_params={"count": 10, "intensity": 3},
    )
    db_session.add(log)
    await db_session.flush()
    await db_session.refresh(log)

    assert log.status == "planned"
    assert log.title_override == "My custom title"
    assert log.scheduled_at is not None
    assert log.planned_comment == "Plan note"
    assert log.completion_comment == "Done note"
    assert log.actual_parameters == {"count": 10, "intensity": 3}
    assert log.updated_at is not None


# ── ADR-040: audit journal ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_history_records_transition(db_session, test_user):
    """ActivityTaskHistory captures prev→new status + snapshot + actor."""
    log = ActivityLog(user_id=test_user.id, status="planned", selected_params={"count": 5})
    db_session.add(log)
    await db_session.flush()

    db_session.add(
        ActivityTaskHistory(
            task_id=log.id,
            previous_status="planned",
            new_status="completed",
            actor_id=test_user.id,
            parameter_snapshot=log.selected_params,
            comment="all done",
        )
    )
    await db_session.flush()

    result = await db_session.execute(select(ActivityTaskHistory).where(ActivityTaskHistory.task_id == log.id))
    h = result.scalar_one()
    assert h.previous_status == "planned"
    assert h.new_status == "completed"
    assert h.actor_id == test_user.id
    assert h.parameter_snapshot == {"count": 5}
    assert h.changed_at is not None


# ── ADR-037: session evolution ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_evolution_columns(db_session, test_user):
    """Session stores title, notes, planned times, accepted_at."""
    now = datetime.now(UTC)
    s = ActivitySession(
        owner_id=test_user.id,
        status="created",
        title="Evening scenario",
        notes="Plan notes",
        planned_start_at=now,
        planned_end_at=now + timedelta(hours=1),
    )
    db_session.add(s)
    await db_session.flush()
    await db_session.refresh(s)

    assert s.title == "Evening scenario"
    assert s.notes == "Plan notes"
    assert s.planned_start_at is not None
    assert s.planned_end_at is not None
    assert s.accepted_at is None  # not accepted yet

    s.accepted_at = now
    await db_session.flush()
    await db_session.refresh(s)
    assert s.accepted_at is not None


# ── ADR-038: penalty_enabled on Entity ──────────────────────────────────


@pytest.mark.asyncio
async def test_entity_penalty_enabled_default(db_session, test_user):
    """penalty_enabled defaults to True; can be disabled per activity."""
    e = Entity(real_name="T", category="test", owner_id=test_user.id)
    db_session.add(e)
    await db_session.flush()
    assert e.penalty_enabled is True

    e.penalty_enabled = False
    await db_session.flush()
    await db_session.refresh(e)
    assert e.penalty_enabled is False


# ── slugify ─────────────────────────────────────────────────────────────


def test_slugify_transliterates_russian():
    from app.slugify import slugify

    assert slugify("Тёплое сообщение-комплимент") == "teploe-soobschenie-kompliment"
    assert slugify("10 ударов рукой") == "10-udarov-rukoy"
    assert slugify("   ") == "activity"
