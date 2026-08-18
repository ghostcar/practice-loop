"""Sexual Journal links (Шаг 14b) — media, Tracker activity link, Timer auto-entry.

Covers:
- media: POST /journal/entries/{id}/media → MediaAsset (owner_type=journal_entry)
- activity link: entry.source == "activity", activity_log_id set; cross-user rejected
- timer auto-entry: open_slot with journal_auto rule creates a draft entry;
  close_slot reports pending; complete_entry fills the details
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.locktimer import enums as e
from app.locktimer.services.execution import (
    add_slot_rule,
    close_slot,
    create_draft,
    open_slot,
    start_session,
)
from app.models.activity_log import ActivityLog
from app.models.journal import JournalEntry
from app.models.locktimer import LockSlotOccurrence
from app.models.media import MediaAsset
from app.models.user import User

pytestmark = pytest.mark.anyio

TODAY = datetime.now(UTC).date()
FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


# ─────────────────────────────────────────────────────────────────────────────
# Media binding
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_media_upload_binds_asset(auth_client, test_user, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))
    await auth_client.post("/journal/entries", data={"entry_date": TODAY.isoformat(), "activity_type": "intimacy"})
    entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))).scalar_one()

    png = b"\x89PNG\r\n\x1a\n" + b"fakepngdata"
    resp = await auth_client.post(
        f"/journal/entries/{entry.id}/media",
        files={"file": ("photo.png", io.BytesIO(png), "image/png")},
        data={"caption": "auto"},
    )
    assert resp.status_code == 303, resp.text

    asset = (await db_session.execute(select(MediaAsset).where(MediaAsset.owner_id == test_user.id))).scalar_one()
    assert asset.owner_type == "journal_entry"
    assert asset.owner_ref_id == entry.id
    assert asset.caption == "auto"
    assert asset.state == "ready"

    # visible on the journal page
    page = await auth_client.get("/journal")
    assert page.status_code == 200


@pytest.mark.asyncio
async def test_entry_media_rejects_foreign_entry(auth_client, test_user, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_entry = JournalEntry(user_id=other.id, entry_date=TODAY, status="completed", source="manual")
    db_session.add(other_entry)
    await db_session.flush()

    png = b"\x89PNG\r\n\x1a\n" + b"fakepngdata"
    resp = await auth_client.post(
        f"/journal/entries/{other_entry.id}/media",
        files={"file": ("photo.png", io.BytesIO(png), "image/png")},
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Tracker activity link
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_linked_to_activity(auth_client, test_user, db_session):
    task = ActivityLog(user_id=test_user.id, status="completed")
    db_session.add(task)
    await db_session.flush()

    resp = await auth_client.post(
        "/journal/entries",
        data={"entry_date": TODAY.isoformat(), "activity_type": "intimacy", "activity_log_id": str(task.id)},
    )
    assert resp.status_code == 303, resp.text
    entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))).scalar_one()
    assert entry.activity_log_id == task.id
    assert entry.source == "activity"


@pytest.mark.asyncio
async def test_entry_activity_link_cross_user_rejected(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_task = ActivityLog(user_id=other.id, status="completed")
    db_session.add(other_task)
    await db_session.flush()

    resp = await auth_client.post(
        "/journal/entries",
        data={"entry_date": TODAY.isoformat(), "activity_log_id": str(other_task.id)},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_json_entry_activity_link(auth_client, test_user, db_session):
    task = ActivityLog(user_id=test_user.id, status="completed")
    db_session.add(task)
    await db_session.flush()

    resp = await auth_client.post(
        "/api/v2/journal/entries",
        json={"entry_date": TODAY.isoformat(), "activity_type": "intimacy", "activity_log_id": str(task.id)},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "activity"
    assert resp.json()["activity_log_id"] == str(task.id)


# ─────────────────────────────────────────────────────────────────────────────
# Timer auto-entry (journal_auto slot)
# ─────────────────────────────────────────────────────────────────────────────


async def _started_with_journal_auto_slot(db_session, user: User):
    """Draft with a journal_auto slot rule, started; returns (session, occ)."""
    session = await create_draft(db_session, owner_id=user.id)
    rule = await add_slot_rule(
        db_session,
        session_id=session.id,
        name="Planned window",
        rule_type=e.SLOT_RULE_EVERY_N_DAYS,
        schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
        duration_seconds=1800,
        journal_auto=True,
    )
    assert rule.journal_auto is True
    await start_session(db_session, session_id=session.id, owner_id=user.id, now=FIXED_NOW)
    occ = (
        await db_session.execute(
            select(LockSlotOccurrence)
            .where(
                LockSlotOccurrence.session_id == session.id,
                LockSlotOccurrence.state == e.SLOT_PENDING,
            )
            .order_by(LockSlotOccurrence.planned_open_at)
            .limit(1)
        )
    ).scalar_one()
    opened = await open_slot(db_session, occurrence=occ, owner_id=user.id, now=occ.planned_open_at)
    return session, opened


@pytest.mark.asyncio
async def test_open_journal_auto_slot_creates_draft_entry(db_session, test_user):
    _, occ = await _started_with_journal_auto_slot(db_session, test_user)
    entry = (
        await db_session.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == test_user.id,
                JournalEntry.slot_occurrence_id == occ.id,
            )
        )
    ).scalar_one()
    assert entry.status == "draft"
    assert entry.source == "timer_slot"
    assert entry.timer_session_id == occ.session_id
    assert entry.slot_occurrence_id == occ.id


@pytest.mark.asyncio
async def test_open_journal_auto_slot_idempotent(db_session, test_user):
    _, occ = await _started_with_journal_auto_slot(db_session, test_user)
    # re-open is rejected state-wise, but the helper itself is idempotent — call it again directly
    from app.api.journal import ensure_timer_slot_entry

    await ensure_timer_slot_entry(
        db_session,
        user_id=test_user.id,
        session_id=occ.session_id,
        slot_occurrence_id=occ.id,
        entry_date=TODAY,
    )
    count = (
        (
            await db_session.execute(
                select(JournalEntry).where(
                    JournalEntry.user_id == test_user.id,
                    JournalEntry.slot_occurrence_id == occ.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(count) == 1


@pytest.mark.asyncio
async def test_close_reports_pending_and_complete_fills_details(db_session, test_user):
    _, occ = await _started_with_journal_auto_slot(db_session, test_user)
    await close_slot(db_session, occurrence=occ, owner_id=test_user.id)

    from app.api.journal import get_pending_slot_entry

    pending = await get_pending_slot_entry(
        db_session,
        user_id=test_user.id,
        slot_occurrence_id=occ.id,
    )
    assert pending is not None
    assert pending.status == "draft"

    # complete via form handler

    # call through the HTTP endpoint instead (form)
    import secrets

    from httpx import ASGITransport, AsyncClient

    from app.auth import create_access_token
    from app.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    csrf = secrets.token_hex(32)
    token = create_access_token(test_user.id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers.update({"Cookie": f"access_token={token}; csrf_token={csrf}", "X-CSRF-Token": csrf})
        resp = await client.post(
            f"/journal/entries/{pending.id}/complete",
            data={
                "activity_type": "intimacy",
                "duration_minutes": "30",
                "satisfaction": "5",
                "protection": "condom",
            },
        )
    app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 303, resp.text

    entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.id == pending.id))).scalar_one()
    assert entry.status == "completed"
    assert entry.activity_type == "intimacy"
    assert entry.duration_minutes == 30
    assert entry.satisfaction == 5


@pytest.mark.asyncio
async def test_non_journal_auto_slot_creates_no_entry(db_session, test_user):
    session = await create_draft(db_session, owner_id=test_user.id)
    await add_slot_rule(
        db_session,
        session_id=session.id,
        name="Plain window",
        rule_type=e.SLOT_RULE_EVERY_N_DAYS,
        schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
        duration_seconds=1800,
        journal_auto=False,
    )
    await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
    occ = (
        await db_session.execute(
            select(LockSlotOccurrence)
            .where(LockSlotOccurrence.session_id == session.id)
            .order_by(LockSlotOccurrence.planned_open_at)
            .limit(1)
        )
    ).scalar_one()
    await open_slot(db_session, occurrence=occ, owner_id=test_user.id, now=occ.planned_open_at)
    entries = (
        (await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))).scalars().all()
    )
    assert len(entries) == 0


@pytest.mark.asyncio
async def test_api_close_slot_reports_journal_pending(auth_client, test_user, db_session):
    session, occ = await _started_with_journal_auto_slot(db_session, test_user)
    resp = await auth_client.post(f"/api/v2/locktimer/slot-occurrences/{occ.id}/close")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "closed"
    assert body["journal_pending"] is not None
    assert body["journal_pending"]["url"] == "/journal"


@pytest.mark.asyncio
async def test_json_complete_draft_entry(auth_client, test_user, db_session):
    _, occ = await _started_with_journal_auto_slot(db_session, test_user)
    pending = (
        await db_session.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == test_user.id,
                JournalEntry.slot_occurrence_id == occ.id,
            )
        )
    ).scalar_one()
    resp = await auth_client.post(
        f"/api/v2/journal/entries/{pending.id}/complete",
        json={"activity_type": "intimacy", "satisfaction": 4, "orgasms": 1},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["satisfaction"] == 4
    assert body["slot_occurrence_id"] == str(occ.id)
