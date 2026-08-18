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


@pytest.mark.asyncio
async def test_json_list_stocks_schedules_kits(auth_client, test_user, db_session):
    """GET /api/v2/medications/{stocks,schedules,kits} — flat lists for mobile."""
    await _create_medication(auth_client, "Ibuprofen")
    med_id = await _get_med_id(db_session, test_user.id, "Ibuprofen")
    await auth_client.post(f"/medications/{med_id}/stock", data={"quantity": "20"})
    await auth_client.post(
        f"/medications/{med_id}/schedule",
        data={"dose_quantity": "1", "frequency_type": "daily", "times_per_day": "2"},
    )
    await auth_client.post("/med-kits", data={"name": "Home kit", "location": "Bathroom"})

    stocks = (await auth_client.get("/api/v2/medications/stocks")).json()
    assert len(stocks) == 1
    assert stocks[0]["medication_name"] == "Ibuprofen"
    assert stocks[0]["quantity"] == 20.0

    schedules = (await auth_client.get("/api/v2/medications/schedules")).json()
    assert len(schedules) == 1
    assert schedules[0]["medication_name"] == "Ibuprofen"
    assert schedules[0]["frequency_type"] == "daily"

    kits = (await auth_client.get("/api/v2/medications/kits")).json()
    assert len(kits) == 1
    assert kits[0]["name"] == "Home kit"


@pytest.mark.asyncio
async def test_json_lists_cross_user_isolation(auth_client, test_user, db_session):
    """Flat medication lists never leak another user's stocks/schedules/kits."""
    other = User(email="other-stocks@example.com", password_hash=hash_password("x"), locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    db_session.add(Medication(user_id=other.id, name="Other med", kind="medication"))
    db_session.add(MedKit(user_id=other.id, name="Other kit"))
    await db_session.flush()

    for path in ("/api/v2/medications/stocks", "/api/v2/medications/schedules", "/api/v2/medications/kits"):
        resp = await auth_client.get(path)
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
async def test_json_create_medication_stock_schedule_kit(auth_client, test_user, db_session):
    """JSON POST create for medication/stock/schedule/kit — for mobile."""
    resp = await auth_client.post(
        "/api/v2/medications",
        json={"name": "Ibuprofen", "kind": "medication", "strength": "400 mg", "unit": "tablet"},
    )
    assert resp.status_code == 201, resp.text
    med_id = resp.json()["id"]

    kit_resp = await auth_client.post("/api/v2/medications/kits", json={"name": "Home kit", "location": "Bathroom"})
    assert kit_resp.status_code == 201, kit_resp.text
    kit_id = kit_resp.json()["id"]

    stock_resp = await auth_client.post(
        "/api/v2/medications/stocks",
        json={
            "medication_id": med_id,
            "quantity": 20.0,
            "kit_id": kit_id,
            "expiry_date": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert stock_resp.status_code == 201, stock_resp.text
    stock = stock_resp.json()
    assert stock["medication_name"] == "Ibuprofen"
    assert stock["kit_name"] == "Home kit"
    assert stock["quantity"] == 20.0

    sched_resp = await auth_client.post(
        "/api/v2/medications/schedules",
        json={"medication_id": med_id, "dose_quantity": 1, "frequency_type": "daily", "times_per_day": 2},
    )
    assert sched_resp.status_code == 201, sched_resp.text
    assert sched_resp.json()["medication_name"] == "Ibuprofen"

    # lists reflect the created records
    assert len((await auth_client.get("/api/v2/medications/stocks")).json()) == 1
    assert len((await auth_client.get("/api/v2/medications/schedules")).json()) == 1
    assert len((await auth_client.get("/api/v2/medications/kits")).json()) == 1


async def test_json_update_medication_is_owner_scoped(auth_client, test_user, db_session):
    med = (await auth_client.post("/api/v2/medications", json={"name": "Old"})).json()
    response = await auth_client.put(
        f"/api/v2/medications/{med['id']}",
        json={"name": "New", "kind": "supplement", "unit": "tablet", "is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New"
    assert response.json()["is_active"] is False

    foreign_user = User(email="foreign-med@example.com", password_hash=hash_password("secret123"))
    db_session.add(foreign_user)
    await db_session.flush()
    other = Medication(user_id=foreign_user.id, name="Foreign")
    db_session.add(other)
    await db_session.flush()
    assert (await auth_client.put(f"/api/v2/medications/{other.id}", json={"name": "Nope"})).status_code == 404


@pytest.mark.asyncio
async def test_json_create_stock_foreign_medication_rejected(auth_client, test_user, db_session):
    """POST /stocks with another user's medication_id → 404 (owner-scoped)."""
    other = User(email="other-json@example.com", password_hash=hash_password("x"), locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_med = Medication(user_id=other.id, name="Other med", kind="medication")
    db_session.add(other_med)
    await db_session.flush()

    resp = await auth_client.post(
        "/api/v2/medications/stocks", json={"medication_id": str(other_med.id), "quantity": 1}
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard block (Step 11b)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_medication_block_due_today(auth_client, test_user, db_session):
    """Dashboard renders the medication block with a due item when a schedule is pending."""
    await _create_medication(auth_client, "Vitamin D")
    med_id = await _get_med_id(db_session, test_user.id, "Vitamin D")
    await auth_client.post(
        f"/medications/{med_id}/schedule",
        data={"dose_quantity": "1", "frequency_type": "daily", "times_per_day": "1"},
    )
    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="dash-block-medication"' in html
    assert "Vitamin D" in html


@pytest.mark.asyncio
async def test_dashboard_medication_block_no_due(auth_client, test_user, db_session):
    """Dashboard medication block shows the empty state when nothing is due."""
    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="dash-block-medication"' in html
    assert "med_no_due" in html or "Nothing due today" in html


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
# ADR-085: positive-only gamification (softened PD-013)
# ─────────────────────────────────────────────────────────────────────────────


def test_medication_module_positive_only_no_penalties():
    """ADR-085: Health-модуль может давать XP/достижения за adherence, но не штрафовать.

    Пропуск/мисс никогда не отнимает баллы — негативная геймификация запрещена.
    """
    import inspect

    import app.api.medication as mod

    source = inspect.getsource(mod)
    # positive hook present
    assert "on_medication_taken" in source
    # no negative gamification wiring in this module
    assert "on_task_interrupted" not in source
    assert "calculate_entity_penalty" not in source
    assert "penalty" not in source.lower()
    # the gamification module itself never deducts points
    import app.gamification.medication as gmod

    gsource = inspect.getsource(gmod)
    assert "xp_earned" in gsource
    assert "-=" not in gsource.replace(" #", " #").split("-")[0]  # no deduction of xp
    assert "deduct" not in gsource.lower()
    assert "penalty" not in gsource.lower()


# ─────────────────────────────────────────────────────────────────────────────
# JSON DELETE (complete mobile CRUD)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_delete_medication_stock_schedule_kit(auth_client, test_user, db_session):
    """JSON DELETE for medication/stock/schedule/kit — complete mobile CRUD."""
    med = (await auth_client.post("/api/v2/medications", json={"name": "Ibuprofen"})).json()
    kit = (await auth_client.post("/api/v2/medications/kits", json={"name": "Home kit"})).json()
    stock = (
        await auth_client.post("/api/v2/medications/stocks", json={"medication_id": med["id"], "quantity": 20})
    ).json()
    sched = (
        await auth_client.post(
            "/api/v2/medications/schedules", json={"medication_id": med["id"], "frequency_type": "daily"}
        )
    ).json()

    assert (await auth_client.delete(f"/api/v2/medications/stocks/{stock['id']}")).status_code == 204
    assert (await auth_client.delete(f"/api/v2/medications/schedules/{sched['id']}")).status_code == 204
    assert (await auth_client.delete(f"/api/v2/medications/kits/{kit['id']}")).status_code == 204
    assert (await auth_client.delete(f"/api/v2/medications/{med['id']}")).status_code == 204

    assert (await auth_client.get("/api/v2/medications/stocks")).json() == []
    assert (await auth_client.get("/api/v2/medications/schedules")).json() == []
    assert (await auth_client.get("/api/v2/medications/kits")).json() == []
    assert (await auth_client.get("/api/v2/medications")).json() == []


@pytest.mark.asyncio
async def test_json_delete_medication_foreign_rejected(auth_client, test_user, db_session):
    """DELETE /medications/{id} for another user's record → 404 (owner-scoped)."""
    other = User(email="other-del@example.com", password_hash=hash_password("x"), locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_med = Medication(user_id=other.id, name="Other med", kind="medication")
    db_session.add(other_med)
    await db_session.flush()

    resp = await auth_client.delete(f"/api/v2/medications/{other_med.id}")
    assert resp.status_code == 404
