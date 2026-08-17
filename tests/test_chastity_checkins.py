"""Tests for C2/B3 — chastity wear check-ins (PRODUCT_OVERVIEW §6.6, Q13).

Relief-only (PD-013): регулярный check-in ношения (состояние/комфорт/отчёт)
+ опциональная LLM-верификация фото через media_verify. Эти тесты фиксируют
data-контракт (создание/листинг/удаление/изоляция) и guard-пути верификации
(LLM-вызов в тестах не выполняется).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.chastity import ChastityCheckIn


@pytest.mark.asyncio
async def test_json_create_list_delete_checkin(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/chastity/check-ins",
        json={"mood": 3, "comfort_level": 4, "notes": "all fine"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mood"] == 3
    assert body["comfort_level"] == 4
    assert body["session_id"] is None

    listed = (await auth_client.get("/api/v2/chastity/check-ins")).json()
    assert len(listed) == 1
    assert listed[0]["notes"] == "all fine"

    assert (await auth_client.delete(f"/api/v2/chastity/check-ins/{body['id']}")).status_code == 204
    assert (await auth_client.get("/api/v2/chastity/check-ins")).json() == []


@pytest.mark.asyncio
async def test_json_checkin_invalid_scale_rejected(auth_client, test_user, db_session):
    # pydantic field constraint → 422
    assert (await auth_client.post("/api/v2/chastity/check-ins", json={"mood": 9})).status_code == 422


@pytest.mark.asyncio
async def test_form_handler_adds_checkin(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/chastity-checkins",
        data={"mood": "4", "comfort_level": "2", "notes": "ok"},
    )
    assert resp.status_code == 303
    rows = (
        await db_session.execute(select(ChastityCheckIn).where(ChastityCheckIn.user_id == test_user.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].mood == 4
    assert rows[0].comfort_level == 2


@pytest.mark.asyncio
async def test_verify_without_media_and_missing_checkin(auth_client, test_user, db_session):
    # missing check-in → 404
    assert (
        await auth_client.post(f"/api/v2/chastity/check-ins/{uuid.uuid4()}/verify", json={})
    ).status_code == 404

    # existing check-in without photo → 400
    c = ChastityCheckIn(user_id=test_user.id, mood=3)
    db_session.add(c)
    await db_session.flush()
    assert (
        await auth_client.post(f"/api/v2/chastity/check-ins/{c.id}/verify", json={})
    ).status_code == 400


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session):
    db_session.add(ChastityCheckIn(user_id=test_user.id, mood=2))
    await db_session.flush()

    import secrets

    from app.auth import create_access_token
    from app.models.user import User

    other = User(email="other-checkin@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    token = create_access_token(other.id)
    csrf = secrets.token_hex(32)
    auth_client.headers["Cookie"] = f"access_token={token}; csrf_token={csrf}"
    auth_client.headers["X-CSRF-Token"] = csrf

    assert (await auth_client.get("/api/v2/chastity/check-ins")).json() == []
