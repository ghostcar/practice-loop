"""Tests for chart endpoints — device-timezone day bucketing (ADR-066).

The 4 daily-series endpoints bucket by the *device's* calendar day
(``local_date(created_at)``), not the database's UTC date. These tests freeze
the clock so a record whose UTC date differs from its device-local date is
deterministically attributed to the device-local day.

Scenario: FROZEN_NOW = 2026-08-13 16:30 UTC.
- UTC           → "today" is 2026-08-13.
- Asia/Tokyo    → "today" is 2026-08-14 (16:30 UTC + 9h = 01:30 Aug 14).
A record at 16:00 UTC on Aug 13 is therefore Aug 13 in UTC but Aug 14 in Tokyo.

Note: ``RECORD_AT`` is deliberately kept well inside the cutoff window — the
``created_at >= cutoff`` filter compares a naive record string against an
aware cutoff string in SQLite, so a record placed on the boundary could be
lexicographically mis-excluded.
"""

from datetime import UTC, date, datetime

import pytest

from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.points import PointsTransaction

FROZEN_NOW = datetime(2026, 8, 13, 16, 30, 0, tzinfo=UTC)
RECORD_AT = datetime(2026, 8, 13, 16, 0, 0)  # naive → assumed UTC (SQLite)


class _FrozenDateTime:
    """Stand-in for ``datetime`` whose ``.now()`` returns a fixed instant."""

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FROZEN_NOW
        return FROZEN_NOW.astimezone(tz)


@pytest.fixture
def freeze_clock(monkeypatch):
    """Freeze ``datetime.now`` in the modules the chart pipeline reads."""
    monkeypatch.setattr("app.timeutils.datetime", _FrozenDateTime)
    monkeypatch.setattr("app.api.points.charts.datetime", _FrozenDateTime)
    yield FROZEN_NOW


def _cookie_with_tz(auth_headers: dict, tz: str | None) -> dict:
    cookie = auth_headers["Cookie"]
    if tz is not None:
        cookie += f"; client_tz={tz}"
    return {"Cookie": cookie}


# ── Activity chart ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_chart_buckets_by_device_tz(
    async_client, auth_headers, db_session, test_user, freeze_clock
) -> None:
    """A record past UTC midnight lands on the device-local 'today' day."""
    db_session.add_all(
        [
            ActivityLog(user_id=test_user.id, status="completed", created_at=RECORD_AT),
            ActivityLog(user_id=test_user.id, status="stopped", created_at=RECORD_AT),
        ]
    )
    await db_session.flush()

    resp = await async_client.get("/api/v2/charts/activity?days=2", headers=_cookie_with_tz(auth_headers, "Asia/Tokyo"))
    assert resp.status_code == 200
    data = resp.json()

    # Tokyo 'today' is Aug 14; the 16:00 UTC records are Aug 14 in Tokyo.
    assert data["labels"] == [
        date(2026, 8, 13).strftime("%a %d"),
        date(2026, 8, 14).strftime("%a %d"),
    ]
    assert data["completed"] == [0, 1]
    assert data["stopped"] == [0, 1]
    assert data["planned"] == [0, 0]


@pytest.mark.asyncio
async def test_activity_chart_default_utc(async_client, auth_headers, db_session, test_user, freeze_clock) -> None:
    """Without a client_tz cookie the same record stays on its UTC day."""
    db_session.add(ActivityLog(user_id=test_user.id, status="completed", created_at=RECORD_AT))
    await db_session.flush()

    resp = await async_client.get("/api/v2/charts/activity?days=2", headers=_cookie_with_tz(auth_headers, None))
    assert resp.status_code == 200
    data = resp.json()

    assert data["labels"][-1] == date(2026, 8, 13).strftime("%a %d")
    assert data["completed"] == [0, 1]


# ── Points trend ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_points_trend_buckets_by_device_tz(
    async_client, auth_headers, db_session, test_user, freeze_clock
) -> None:
    db_session.add(
        PointsTransaction(
            user_id=test_user.id,
            amount=50,
            transaction_type="earn",
            created_at=RECORD_AT,
        )
    )
    await db_session.flush()

    resp = await async_client.get(
        "/api/v2/charts/points-trend?days=2", headers=_cookie_with_tz(auth_headers, "Asia/Tokyo")
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["labels"] == [
        date(2026, 8, 13).strftime("%d %b"),
        date(2026, 8, 14).strftime("%d %b"),
    ]
    assert data["balance"] == [0, 50]
    assert data["breakdown"] == {"earn": 50}


# ── XP history ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_xp_history_buckets_by_device_tz(async_client, auth_headers, db_session, test_user, freeze_clock) -> None:
    db_session.add(
        ActivityLog(
            user_id=test_user.id,
            status="completed",
            points_awarded=25,
            created_at=RECORD_AT,
        )
    )
    await db_session.flush()

    resp = await async_client.get(
        "/api/v2/charts/xp-history?days=2", headers=_cookie_with_tz(auth_headers, "Asia/Tokyo")
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["labels"] == [
        date(2026, 8, 13).strftime("%a"),
        date(2026, 8, 14).strftime("%a"),
    ]
    assert data["values"] == [0, 25]


# ── Completion rate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_completion_rate_buckets_by_device_tz(
    async_client, auth_headers, db_session, test_user, freeze_clock
) -> None:
    db_session.add_all(
        [
            ActivityLog(user_id=test_user.id, status="completed", created_at=RECORD_AT),
            ActivityLog(user_id=test_user.id, status="planned", created_at=RECORD_AT),
        ]
    )
    await db_session.flush()

    resp = await async_client.get(
        "/api/v2/charts/completion-rate?days=2", headers=_cookie_with_tz(auth_headers, "Asia/Tokyo")
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["labels"][-1] == date(2026, 8, 14).strftime("%a")
    assert data["rates"] == [0, 50]
    assert data["overall_rate"] == 50
    assert data["completed_tasks"] == 1
    assert data["total_tasks"] == 2


# ── Category breakdown (not day-bucketed) ──────────────────────────


@pytest.mark.asyncio
async def test_category_breakdown_groups_by_category(async_client, auth_headers, db_session, test_user) -> None:
    """Category distribution groups by Entity.category (independent of device tz)."""
    cardio = Entity(real_name="Cardio run", category="cardio")
    strength = Entity(real_name="Squats", category="strength")
    db_session.add_all([cardio, strength])
    await db_session.flush()

    recent = datetime.now(UTC).replace(tzinfo=None)  # naive "now" (SQLite storage)
    db_session.add_all(
        [
            ActivityLog(user_id=test_user.id, entity_id=cardio.id, status="completed", created_at=recent),
            ActivityLog(user_id=test_user.id, entity_id=cardio.id, status="completed", created_at=recent),
            ActivityLog(user_id=test_user.id, entity_id=strength.id, status="completed", created_at=recent),
        ]
    )
    await db_session.flush()

    resp = await async_client.get(
        "/api/v2/charts/category-breakdown?days=30",
        headers={"Cookie": auth_headers["Cookie"]},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 3
    assert data["labels"] == ["cardio", "strength"]  # ordered by count desc
    assert data["values"] == [2, 1]
