"""Tests for B2 — chastity device care events (PRODUCT_OVERVIEW §6.2).

Relief-only (PD-013): журнал ухода за устройством (комфорт/проблемы/
обслуживание) без игровой интеграции.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import ChastityDeviceEvent
from app.models.life import InventoryItem
from app.models.user import User


def _make_device(db: AsyncSession, user: User) -> InventoryItem:
    item = InventoryItem(
        user_id=user.id, category="wearable", name="Steel cage", quantity=1, status="bought"
    )
    db.add(item)
    return item


@pytest.mark.asyncio
async def test_json_create_list_delete_event(auth_client, test_user, db_session):
    dev = _make_device(db_session, test_user)
    await db_session.flush()

    resp = await auth_client.post(
        "/api/v2/devices/events",
        json={"event_type": "comfort", "device_id": str(dev.id), "comfort_level": 4, "notes": "ok"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["event_type"] == "comfort"
    assert body["comfort_level"] == 4
    assert body["device_id"] == str(dev.id)

    listed = (await auth_client.get(f"/api/v2/devices/events?device_id={dev.id}")).json()
    assert len(listed) == 1

    assert (await auth_client.delete(f"/api/v2/devices/events/{body['id']}")).status_code == 204
    assert (await auth_client.get(f"/api/v2/devices/events?device_id={dev.id}")).json() == []


@pytest.mark.asyncio
async def test_json_event_foreign_device_rejected(auth_client, test_user, db_session):
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_dev = InventoryItem(user_id=other.id, category="wearable", name="X", quantity=1, status="bought")
    db_session.add(other_dev)
    await db_session.flush()

    resp = await auth_client.post(
        "/api/v2/devices/events",
        json={"event_type": "comfort", "device_id": str(other_dev.id)},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_json_invalid_event_type_and_comfort(auth_client, test_user, db_session):
    assert (await auth_client.post("/api/v2/devices/events", json={"event_type": "bogus"})).status_code == 400
    # out-of-range comfort rejected by the pydantic field constraint (422)
    assert (
        await auth_client.post("/api/v2/devices/events", json={"event_type": "comfort", "comfort_level": 9})
    ).status_code == 422


@pytest.mark.asyncio
async def test_form_handler_adds_event(auth_client, test_user, db_session):
    dev = _make_device(db_session, test_user)
    await db_session.flush()
    resp = await auth_client.post(
        "/device-events",
        data={"event_type": "problem", "device_id": str(dev.id), "severity": "medium", "notes": "pinching"},
    )
    assert resp.status_code == 303
    evs = (
        await db_session.execute(select(ChastityDeviceEvent).where(ChastityDeviceEvent.user_id == test_user.id))
    ).scalars().all()
    assert len(evs) == 1
    assert evs[0].severity == "medium"
    assert evs[0].device_id == dev.id


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session):
    db_session.add(ChastityDeviceEvent(user_id=test_user.id, event_type="comfort", comfort_level=5))
    await db_session.flush()
    other = User(email="other2@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    import secrets

    from app.auth import create_access_token

    token = create_access_token(other.id)
    csrf = secrets.token_hex(32)
    auth_client.headers["Cookie"] = f"access_token={token}; csrf_token={csrf}"
    auth_client.headers["X-CSRF-Token"] = csrf

    assert (await auth_client.get("/api/v2/devices/events")).json() == []
