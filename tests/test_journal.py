"""Sexual Journal tests (M3 Personal Suite, Шаг 14, ROADMAP §7 4A).

Relief-only: журнал без игровой интеграции (PD-013). Приватные записи,
связи с Timer/Health — по ID без раскрытия (DATA_LIFECYCLE.md).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.journal import JournalEntry, JournalPartner
from app.models.user import User

TODAY = date.today()


# ─────────────────────────────────────────────────────────────────────────────
# Page + entries
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_journal_page_empty(auth_client, test_user, db_session):
    resp = await auth_client.get("/journal")
    assert resp.status_code == 200
    assert "journal_no_entries" in resp.text or "No entries yet" in resp.text


@pytest.mark.asyncio
async def test_add_entry_and_list(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/journal/entries",
        data={
            "entry_date": TODAY.isoformat(),
            "activity_type": "intimacy",
            "duration_minutes": "45",
            "desire_before": "4",
            "arousal_before": "5",
            "protection": "condom",
            "orgasms": "2",
            "intensity": "4",
            "satisfaction": "5",
            "pleasure": "4",
            "reactions": "pleasure, pain",
            "emotional_state": "connected, calm",
            "aftercare": "cuddling",
            "recovery": "4",
            "notes": "great evening",
        },
    )
    assert resp.status_code == 303, resp.text
    entries = (
        await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))
    ).scalars().all()
    assert len(entries) == 1
    e = entries[0]
    assert e.activity_type == "intimacy"
    assert e.duration_minutes == 45
    assert e.desire_before == 4
    assert e.protection == "condom"
    assert e.orgasms == 2
    assert e.reactions == ["pleasure", "pain"]
    assert e.emotional_state == ["connected", "calm"]
    assert e.aftercare == "cuddling"

    resp = await auth_client.get("/journal")
    assert resp.status_code == 200
    assert "intimacy" in resp.text
    assert "great evening" in resp.text


@pytest.mark.asyncio
async def test_invalid_scale_rejected(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/journal/entries", data={"entry_date": TODAY.isoformat(), "satisfaction": "9"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_entry(auth_client, test_user, db_session):
    await auth_client.post(
        "/journal/entries", data={"entry_date": TODAY.isoformat(), "activity_type": "massage"}
    )
    entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))).scalar_one()
    resp = await auth_client.post(f"/journal/entries/{entry.id}/delete")
    assert resp.status_code == 303
    remaining = (
        await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))
    ).scalars().all()
    assert len(remaining) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Partners
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_partner_and_link_entry(auth_client, test_user, db_session):
    resp = await auth_client.post("/journal/partners", data={"name": "M.", "notes": "local alias"})
    assert resp.status_code == 303, resp.text
    partner = (
        await db_session.execute(select(JournalPartner).where(JournalPartner.user_id == test_user.id))
    ).scalar_one()
    assert partner.name == "M."

    resp = await auth_client.post(
        "/journal/entries",
        data={"entry_date": TODAY.isoformat(), "partner_id": str(partner.id), "activity_type": "intimacy"},
    )
    assert resp.status_code == 303, resp.text
    entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))).scalar_one()
    assert entry.partner_id == partner.id

    resp = await auth_client.get("/journal")
    assert resp.status_code == 200
    assert "M." in resp.text


@pytest.mark.asyncio
async def test_foreign_partner_rejected(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_partner = JournalPartner(user_id=other.id, name="X")
    db_session.add(other_partner)
    await db_session.flush()

    resp = await auth_client.post(
        "/journal/entries", data={"entry_date": TODAY.isoformat(), "partner_id": str(other_partner.id)}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_partner_sets_null(auth_client, test_user, db_session):
    await auth_client.post("/journal/partners", data={"name": "M."})
    partner = (
        await db_session.execute(select(JournalPartner).where(JournalPartner.user_id == test_user.id))
    ).scalar_one()
    await auth_client.post(
        "/journal/entries",
        data={"entry_date": TODAY.isoformat(), "partner_id": str(partner.id)},
    )
    resp = await auth_client.post(f"/journal/partners/{partner.id}/delete")
    assert resp.status_code == 303
    entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))).scalar_one()
    assert entry.partner_id is None  # SET NULL — связь по ID без раскрытия


# ─────────────────────────────────────────────────────────────────────────────
# Cycle phase snapshot (связь Sexual Journal ↔ Cycle, §16)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_snapshots_cycle_phase(auth_client, test_user, db_session):
    # bleeding 5 days ago → day 6 → follicular (period 5, cycle 28)
    start = TODAY - timedelta(days=5)
    await auth_client.post("/health/cycle/events", data={"event_date": start.isoformat(), "event_type": "bleeding"})
    await auth_client.post("/journal/entries", data={"entry_date": TODAY.isoformat(), "activity_type": "intimacy"})
    entry = (await db_session.execute(select(JournalEntry).where(JournalEntry.user_id == test_user.id))).scalar_one()
    assert entry.cycle_phase == "follicular"
    assert entry.cycle_day == 6


# ─────────────────────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_summary_and_add_entry(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/journal/entries",
        json={"entry_date": TODAY.isoformat(), "activity_type": "intimacy", "satisfaction": 5, "orgasms": 1},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["satisfaction"] == 5
    assert body["activity_type"] == "intimacy"

    resp = await auth_client.get("/api/v2/journal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entries"][0]["satisfaction"] == 5


@pytest.mark.asyncio
async def test_json_add_partner(auth_client, test_user, db_session):
    resp = await auth_client.post("/api/v2/journal/partners", json={"name": "A."})
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "A."


@pytest.mark.asyncio
async def test_json_invalid_protection_defaults(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/journal/entries", json={"entry_date": TODAY.isoformat(), "protection": "bogus"}
    )
    assert resp.status_code == 201
    assert resp.json()["protection"] == "none"


# ─────────────────────────────────────────────────────────────────────────────
# Cross-user isolation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session):
    await auth_client.post(
        "/journal/entries", data={"entry_date": TODAY.isoformat(), "activity_type": "private"}
    )
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    import secrets

    from app.auth import create_access_token

    token = create_access_token(other.id)
    csrf = secrets.token_hex(32)
    auth_client.headers["Cookie"] = f"access_token={token}; csrf_token={csrf}"
    auth_client.headers["X-CSRF-Token"] = csrf

    resp = await auth_client.get("/api/v2/journal")
    assert resp.status_code == 200
    assert not any(e["activity_type"] == "private" for e in resp.json()["entries"])


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard block
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_journal_block(auth_client, test_user, db_session):
    await auth_client.post(
        "/journal/entries",
        data={"entry_date": TODAY.isoformat(), "activity_type": "intimacy", "satisfaction": "5"},
    )
    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="dash-block-journal"' in html
    assert "dash_journal_entries_30d" in html or "entries in 30d" in html


@pytest.mark.asyncio
async def test_dashboard_journal_block_empty(auth_client, test_user, db_session):
    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    assert 'id="dash-block-journal"' in resp.text
    assert "dash_journal_empty" in resp.text or "No entries yet" in resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Relief-only boundary (PD-013)
# ─────────────────────────────────────────────────────────────────────────────


def test_journal_module_no_gamification():
    """PD-013: журнал не применяет игровую механику (по импортам и вызовам)."""
    import inspect

    import app.api.journal as mod

    source = inspect.getsource(mod)
    assert "app.gamification" not in source
    assert "app.models.points" not in source
    assert "app.models.progress" not in source
    assert "award_points" not in source
    assert "apply_penalty" not in source
    assert "calculate_entity_penalty" not in source
