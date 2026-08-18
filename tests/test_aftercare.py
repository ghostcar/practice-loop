"""Tests for C1 — Aftercare module (relief-only, PD-013).

Структурированный журнал заботы после сцены: физическая/эмоциональная забота,
дебриф, гидратация, отдых. Мягкая связь с Sexual Journal (FK SET NULL) и
Chastity Timer (по ID без FK).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.aftercare import AftercareEntry
from app.models.journal import JournalEntry
from app.models.user import User


@pytest.mark.asyncio
async def test_json_create_list_delete(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/aftercare/entries",
        json={"kind": "emotional", "comfort_level": 4, "notes": "debrief done"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "emotional"
    assert body["comfort_level"] == 4

    listed = (await auth_client.get("/api/v2/aftercare")).json()
    assert listed["total"] == 1
    assert listed["entries"][0]["notes"] == "debrief done"

    assert (await auth_client.delete(f"/api/v2/aftercare/entries/{body['id']}")).status_code == 204
    assert (await auth_client.get("/api/v2/aftercare")).json()["total"] == 0


@pytest.mark.asyncio
async def test_json_link_journal_and_invalid_kind(auth_client, test_user, db_session):
    je = JournalEntry(user_id=test_user.id, entry_date=date(2026, 8, 17))
    db_session.add(je)
    await db_session.flush()

    resp = await auth_client.post(
        "/api/v2/aftercare/entries",
        json={"kind": "physical", "journal_entry_id": str(je.id)},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["journal_entry_id"] == str(je.id)

    assert (await auth_client.post("/api/v2/aftercare/entries", json={"kind": "bogus"})).status_code == 400


@pytest.mark.asyncio
async def test_json_foreign_journal_rejected(auth_client, test_user, db_session):
    other = User(email="other-af@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_je = JournalEntry(user_id=other.id, entry_date=date(2026, 8, 17))
    db_session.add(other_je)
    await db_session.flush()

    resp = await auth_client.post(
        "/api/v2/aftercare/entries",
        json={"kind": "rest", "journal_entry_id": str(other_je.id)},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_form_handler_adds_entry(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/aftercare/entries",
        data={"kind": "hydration", "comfort_level": "5", "notes": "water"},
    )
    assert resp.status_code == 303
    rows = (
        (await db_session.execute(select(AftercareEntry).where(AftercareEntry.user_id == test_user.id))).scalars().all()
    )
    assert len(rows) == 1
    assert rows[0].kind == "hydration"
    assert rows[0].comfort_level == 5


@pytest.mark.asyncio
async def test_page_renders(auth_client, test_user, db_session):
    resp = await auth_client.get("/aftercare")
    assert resp.status_code == 200
    assert "aftercare" in resp.text


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session):
    db_session.add(AftercareEntry(user_id=test_user.id, entry_date=date(2026, 8, 17), kind="rest"))
    await db_session.flush()

    import secrets

    from app.auth import create_access_token
    from app.models.user import User

    other = User(email="other-af2@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    token = create_access_token(other.id)
    csrf = secrets.token_hex(32)
    auth_client.headers["Cookie"] = f"access_token={token}; csrf_token={csrf}"
    auth_client.headers["X-CSRF-Token"] = csrf

    assert (await auth_client.get("/api/v2/aftercare")).json()["total"] == 0
