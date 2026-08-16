"""Medication Organizer tests (M3 Personal Suite, Шаг 11b).

Relief-only: Health-модуль без игровой интеграции (PD-013).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.models.medication import Medication, MedIntake, MedKit, MedSchedule
from app.models.user import User


async def _create_medication(client, name: str = "Ibuprofen") -> str:
    resp = await client.post(
        "/medications",
        data={
            "name": name,
            "kind": "medication",
            "strength": "400 mg",
            "unit": "tablet",
            "instructions": "After meals",
        },
    )
    assert resp.status_code == 303, resp.text
    return name


async def _get_med_id(db: AsyncSession, user_id, name: str):
    m = (
        await db.execute(select(Medication).where(Medication.user_id == user_id, Medication.name == name))
    ).scalar_one()
    return m.id


# ─────────────────────────────────────────────────────────────────────────────
# CRUD + list page
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_medication_and_list(auth_client, test_user, db_session):
    await _create_medication(auth_client, "Ibuprofen")
    resp = await auth_client.get("/medications")
    assert resp.status_code == 200
    assert "Ibuprofen" in resp.text
    assert "400 mg" in resp.text


@pytest.mark.asyncio
async def test_create_kit(auth_client, test_user, db_session):
    resp = await auth_client.post("/med-kits", data={"name": "Home kit", "location": "Bathroom"})
    assert resp.status_code == 303
    kits = (await db_session.execute(select(MedKit).where(MedKit.user_id == test_user.id))).scalars().all()
    assert len(kits) == 1
    assert kits[0].name == "Home kit"


@pytest.mark.asyncio
async def test_add_stock_with_expiry_appears_in_summary(auth_client, test_user, db_session):
    await _create_medication(auth_client, "Paracetamol")
    med_id = await _get_med_id(db_session, test_user.id, "Paracetamol")
    expiring = date.today() + timedelta(days=10)
    resp = await auth_client.post(
        f"/medications/{med_id}/stock",
        data={"quantity": "20", "expiry_date": expiring.isoformat(), "low_stock_threshold": "5"},
    )
    assert resp.status_code == 303
    # GET summary
    resp = await auth_client.get("/medications")
    assert resp.status_code == 200
    assert "Paracetamol" in resp.text


@pytest.mark.asyncio
async def test_schedule_due_today(auth_client, test_user, db_session):
    await _create_medication(auth_client, "Vitamin D")
    med_id = await _get_med_id(db_session, test_user.id, "Vitamin D")
    resp = await auth_client.post(
        f"/medications/{med_id}/schedule",
        data={"dose_quantity": "1", "dose_unit": "capsule", "frequency_type": "daily", "times_per_day": "2"},
    )
    assert resp.status_code == 303
    resp = await auth_client.get("/api/v2/medications/today")
    assert resp.status_code == 200
    data = resp.json()
    assert any(d["medication_name"] == "Vitamin D" for d in data["due"])


@pytest.mark.asyncio
async def test_record_intake_clears_due_today(auth_client, test_user, db_session):
    await _create_medication(auth_client, "Magnesium")
    med_id = await _get_med_id(db_session, test_user.id, "Magnesium")
    await auth_client.post(
        f"/medications/{med_id}/schedule",
        data={"dose_quantity": "1", "frequency_type": "daily", "times_per_day": "1"},
    )
    sched = (await db_session.execute(select(MedSchedule).where(MedSchedule.medication_id == med_id))).scalar_one()
    # before intake → due
    before = (await auth_client.get("/api/v2/medications/today")).json()
    assert any(d["medication_name"] == "Magnesium" for d in before["due"])
    # mark taken
    resp = await auth_client.post(
        "/med-intakes",
        data={"medication_id": str(med_id), "schedule_id": str(sched.id), "status": "taken"},
    )
    assert resp.status_code == 303
    after = (await auth_client.get("/api/v2/medications/today")).json()
    assert not any(d["medication_name"] == "Magnesium" for d in after["due"])
    intakes = (await db_session.execute(select(MedIntake).where(MedIntake.user_id == test_user.id))).scalars().all()
    assert len(intakes) == 1
    assert intakes[0].status == "taken"


@pytest.mark.asyncio
async def test_low_stock_appears_in_summary(auth_client, test_user, db_session):
    await _create_medication(auth_client, "Bandage")
    med_id = await _get_med_id(db_session, test_user.id, "Bandage")
    await auth_client.post(
        f"/medications/{med_id}/stock",
        data={"quantity": "1", "low_stock_threshold": "3"},
    )
    data = (await auth_client.get("/api/v2/medications/today")).json()
    assert any(item["medication_name"] == "Bandage" for item in data["low_stock"])


# ─────────────────────────────────────────────────────────────────────────────
# Export (Shared Artifact)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_csv(auth_client, test_user, db_session):
    await _create_medication(auth_client, "Amoxicillin")
    resp = await auth_client.get("/medications/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "Amoxicillin" in resp.text
    assert "attachment" in resp.headers["content-disposition"]


# ─────────────────────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_api_list_and_record_intake(auth_client, test_user, db_session):
    await _create_medication(auth_client, "Iodine")
    med_id = await _get_med_id(db_session, test_user.id, "Iodine")
    resp = await auth_client.get("/api/v2/medications")
    assert resp.status_code == 200
    assert any(m["name"] == "Iodine" for m in resp.json())

    resp = await auth_client.post(
        f"/api/v2/medications/{med_id}/intake",
        json={"status": "taken", "quantity_taken": 1.0},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "taken"
    assert body["medication_id"] == str(med_id)


# ─────────────────────────────────────────────────────────────────────────────
# Cross-user isolation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session):
    await _create_medication(auth_client, "Private Med")
    # second user
    other = User(email="other@example.com", password_hash=hash_password("secret123"), locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    resp = await auth_client.get("/api/v2/medications")
    assert any(m["name"] == "Private Med" for m in resp.json())

    # switch auth to other user
    import secrets

    from app.auth import create_access_token

    token = create_access_token(other.id)
    csrf = secrets.token_hex(32)
    auth_client.headers["Cookie"] = f"access_token={token}; csrf_token={csrf}"
    auth_client.headers["X-CSRF-Token"] = csrf

    resp = await auth_client.get("/api/v2/medications")
    assert resp.status_code == 200
    assert not any(m["name"] == "Private Med" for m in resp.json())


# ─────────────────────────────────────────────────────────────────────────────
# Relief-only: no gamification integration in the medication module
# ─────────────────────────────────────────────────────────────────────────────


def test_medication_module_has_no_gamification_import():
    """PD-013: Health-модуль не должен импортировать gamification."""
    import inspect

    import app.api.medication as mod

    source = inspect.getsource(mod)
    assert "gamification" not in source
    assert "xp" not in source.lower().split()  # no XP wiring
    assert "penalty" not in source.lower()
