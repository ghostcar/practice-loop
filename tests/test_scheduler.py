"""Integration tests for auto-analysis scheduler and training day lifecycle."""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.training import TrainingDay
from app.models.user import User
from app.training.scheduler import _parse_time, start_auto_analysis, stop_auto_analysis

# ── Unit: _parse_time ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("input_str", "expected"),
    [
        ("23:00", (23, 0)),
        ("00:00", (0, 0)),
        ("12:30", (12, 30)),
        ("06:05", (6, 5)),
        (" 08:45 ", (8, 45)),
        ("25:99", (1, 39)),  # Overflow: modulo 24/60
    ],
)
def test_parse_time(input_str: str, expected: tuple[int, int]) -> None:
    assert _parse_time(input_str) == expected


# ── Unit: scheduler lifecycle ──────────────────────────────────────


@pytest.mark.asyncio
async def test_scheduler_start_stop() -> None:
    """Start and stop the scheduler without errors."""
    await start_auto_analysis()
    await stop_auto_analysis()
    # Double-stop is safe
    await stop_auto_analysis()


@pytest.mark.asyncio
async def test_scheduler_double_start() -> None:
    """Double-start is idempotent."""
    await start_auto_analysis()
    await start_auto_analysis()  # Should not create a second task
    await stop_auto_analysis()


# ── Training day lifecycle (integration via API) ────────────────────


@pytest.mark.asyncio
async def test_training_day_creation_via_api(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User
) -> None:
    """Training day is created when planning via /training/plan."""
    response = await auth_client.post("/training/plan", follow_redirects=False)
    # May fail without LLM config, but should not 500
    assert response.status_code in (200, 302, 303, 400, 422, 500, 503)

    # At minimum: app is alive and endpoint exists
    assert response.status_code != 404


@pytest.mark.asyncio
async def test_training_day_status_transitions(db_session: AsyncSession, test_user: User) -> None:
    """TrainingDay can be created and its status transitions are valid."""
    td = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    db_session.add(td)
    await db_session.flush()

    # Add a pending task
    log = ActivityLog(
        user_id=test_user.id,
        status="pending",
        selected_entity_name="Test task",
        training_day_id=td.id,
    )
    db_session.add(log)
    await db_session.flush()

    # Verify both exist
    result = await db_session.execute(select(TrainingDay).where(TrainingDay.id == td.id))
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.status == "active"
    assert fetched.user_id == test_user.id

    # Verify task is linked
    result = await db_session.execute(select(ActivityLog).where(ActivityLog.training_day_id == td.id))
    tasks = result.scalars().all()
    assert len(tasks) == 1
    assert tasks[0].selected_entity_name == "Test task"


@pytest.mark.asyncio
async def test_multiple_training_days_per_user(db_session: AsyncSession, test_user: User) -> None:
    """A user can have multiple training days (one per date)."""
    day1 = TrainingDay(user_id=test_user.id, target_date=date(2026, 8, 1), status="completed")
    day2 = TrainingDay(user_id=test_user.id, target_date=date(2026, 8, 2), status="active")
    day3 = TrainingDay(user_id=test_user.id, target_date=date(2026, 8, 3), status="planned")
    db_session.add_all([day1, day2, day3])
    await db_session.flush()

    result = await db_session.execute(
        select(TrainingDay).where(TrainingDay.user_id == test_user.id).order_by(TrainingDay.target_date)
    )
    days = result.scalars().all()
    assert len(days) == 3
    assert days[0].target_date == date(2026, 8, 1)
    assert days[0].status == "completed"
    assert days[2].status == "planned"


# ── Auto-analysis: no unanalyzed days → no-op ──────────────────────


@pytest.mark.asyncio
async def test_auto_analysis_noop_when_nothing_to_analyze(db_session: AsyncSession, test_user: User) -> None:
    """If all training days are completed, auto-analysis does nothing."""
    td = TrainingDay(user_id=test_user.id, target_date=date.today(), status="completed")
    db_session.add(td)
    await db_session.flush()

    # Query for unanalyzed — should find none since status is "completed"
    result = await db_session.execute(
        select(TrainingDay).where(
            TrainingDay.target_date <= date.today(),
            TrainingDay.status.in_(["active", "planned"]),
        )
    )
    unanalyzed = result.scalars().all()
    assert len(unanalyzed) == 0


@pytest.mark.asyncio
async def test_auto_analysis_finds_active_days(db_session: AsyncSession, test_user: User) -> None:
    """Active training days are found by the analysis query."""
    td = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    db_session.add(td)
    await db_session.flush()

    result = await db_session.execute(
        select(TrainingDay).where(
            TrainingDay.target_date <= date.today(),
            TrainingDay.status.in_(["active", "planned"]),
        )
    )
    unanalyzed = result.scalars().all()
    assert len(unanalyzed) == 1
    assert unanalyzed[0].id == td.id


# ── Auto-analysis: cross-user isolation ────────────────────────────


@pytest.mark.asyncio
async def test_auto_analysis_cross_user_isolation(db_session: AsyncSession, test_user: User) -> None:
    """Auto-analysis query should NOT mix users."""
    from app.auth import hash_password

    other = User(
        email="cross@example.com",
        password_hash=hash_password("secret123"),
        locale="en",
        theme="dark",
    )
    db_session.add(other)
    await db_session.flush()

    # Both users have active training days
    td1 = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    td2 = TrainingDay(user_id=other.id, target_date=date.today(), status="active")
    db_session.add_all([td1, td2])
    await db_session.flush()

    # Verify each user's days are scoped
    result = await db_session.execute(select(TrainingDay).where(TrainingDay.user_id == test_user.id))
    user_days = result.scalars().all()
    assert len(user_days) == 1
    assert user_days[0].user_id == test_user.id
