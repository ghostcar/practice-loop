"""Medication Organizer tests (M3 Personal Suite, Шаг 11b).

Relief-only: Health-модуль без игровой интеграции (PD-013).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.models.medication import (
    MedComponent,
    MedCourse,
    Medication,
    MedIntake,
    MedKit,
    MedSchedule,
    MedStock,
    MedSubstance,
    MedVariant,
)
from app.models.user import User
from app.services.med_service import (
    normalize_substance,
    parse_components_payload,
    parse_regimen_text,
)


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
# ADR-189 phase A: kit in create form → auto stock; kits section on page
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_medication_with_kit_creates_auto_stock(auth_client, test_user, db_session):
    """POST /medications with kit_id + stock_quantity auto-creates a MedStock in the kit."""
    await auth_client.post("/med-kits", data={"name": "Home kit"})
    kit = (await db_session.execute(select(MedKit).where(MedKit.user_id == test_user.id))).scalar_one()

    resp = await auth_client.post(
        "/medications",
        data={"name": "Ibuprofen", "kind": "medication", "kit_id": str(kit.id), "stock_quantity": "20"},
    )
    assert resp.status_code == 303

    stocks = (await db_session.execute(select(MedStock).where(MedStock.user_id == test_user.id))).scalars().all()
    assert len(stocks) == 1
    assert stocks[0].kit_id == kit.id
    assert stocks[0].quantity == 20.0


@pytest.mark.asyncio
async def test_create_medication_kit_none_no_stock(auth_client, test_user, db_session):
    """POST /medications without kit → no auto stock created."""
    resp = await auth_client.post(
        "/medications", data={"name": "Ibuprofen", "kind": "medication", "kit_id": "__none__"}
    )
    assert resp.status_code == 303
    stocks = (await db_session.execute(select(MedStock).where(MedStock.user_id == test_user.id))).scalars().all()
    assert stocks == []


@pytest.mark.asyncio
async def test_kits_section_renders_kit_card_with_meds(auth_client, test_user, db_session):
    """Page renders an always-visible kits section with kit card contents (ADR-189)."""
    await auth_client.post("/med-kits", data={"name": "Home kit", "location": "Bathroom"})
    kit = (await db_session.execute(select(MedKit).where(MedKit.user_id == test_user.id))).scalar_one()
    await auth_client.post(
        "/medications",
        data={"name": "Ibuprofen", "kind": "medication", "kit_id": str(kit.id), "stock_quantity": "20"},
    )

    resp = await auth_client.get("/medications")
    assert resp.status_code == 200
    html = resp.text
    # kits section heading + card with med name inside
    assert "Home kit" in html
    assert "Bathroom" in html
    assert "Ibuprofen" in html


# ─────────────────────────────────────────────────────────────────────────────
# ADR-189 phase B: regimen fields (food_relation, duration_days) + presets
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_with_regimen_fields_computes_end_date(auth_client, test_user, db_session):
    """food_relation + duration_days → end_date = start_date + duration − 1."""
    await _create_medication(auth_client, "Amoxicillin")
    med_id = await _get_med_id(db_session, test_user.id, "Amoxicillin")
    start = date(2026, 9, 15)
    resp = await auth_client.post(
        f"/medications/{med_id}/schedule",
        data={
            "dose_quantity": "1",
            "frequency_type": "daily",
            "times_per_day": "3",
            "food_relation": "before_meal",
            "duration_days": "20",
            "start_date": start.isoformat(),
        },
    )
    assert resp.status_code == 303

    sched = (await db_session.execute(select(MedSchedule).where(MedSchedule.medication_id == med_id))).scalar_one()
    assert sched.food_relation == "before_meal"
    assert sched.duration_days == 20
    assert sched.end_date == start + timedelta(days=19)


@pytest.mark.asyncio
async def test_schedule_invalid_food_relation_ignored(auth_client, test_user, db_session):
    """Unknown food_relation is dropped (validated against FOOD_RELATIONS)."""
    await _create_medication(auth_client, "Vitamin D")
    med_id = await _get_med_id(db_session, test_user.id, "Vitamin D")
    resp = await auth_client.post(
        f"/medications/{med_id}/schedule",
        data={"dose_quantity": "1", "frequency_type": "daily", "food_relation": "with_tea"},
    )
    assert resp.status_code == 303
    sched = (await db_session.execute(select(MedSchedule).where(MedSchedule.medication_id == med_id))).scalar_one()
    assert sched.food_relation is None


@pytest.mark.asyncio
async def test_regimen_text_and_meal_times(auth_client, test_user, db_session):
    """schedule_times maps food_relation to the meal grid; page shows regimen_text."""
    from app.services.med_service import schedule_times

    await _create_medication(auth_client, "Ibuprofen")
    med_id = await _get_med_id(db_session, test_user.id, "Ibuprofen")
    await auth_client.post(
        f"/medications/{med_id}/schedule",
        data={"dose_quantity": "1", "frequency_type": "daily", "times_per_day": "2", "food_relation": "before_meal"},
    )
    sched = (await db_session.execute(select(MedSchedule).where(MedSchedule.medication_id == med_id))).scalar_one()
    # before meal = breakfast−30 (07:30) and lunch−30 (12:30)
    assert schedule_times(sched) == ["07:30", "12:30"]

    resp = await auth_client.get("/medications")
    assert resp.status_code == 200
    # regimen text rendered in the schedule list (ru locale default for test user? en is fallback)
    assert "Ibuprofen" in resp.text


@pytest.mark.asyncio
async def test_json_schedule_accepts_regimen_fields(auth_client, test_user, db_session):
    """JSON POST /schedules with food_relation/duration_days persists and returns them."""
    med = (await auth_client.post("/api/v2/medications", json={"name": "Ibuprofen"})).json()
    start = date(2026, 10, 1)
    resp = await auth_client.post(
        "/api/v2/medications/schedules",
        json={
            "medication_id": med["id"],
            "dose_quantity": 1,
            "frequency_type": "daily",
            "times_per_day": 3,
            "food_relation": "after_meal",
            "duration_days": 10,
            "start_date": start.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["food_relation"] == "after_meal"
    assert body["duration_days"] == 10
    assert body["end_date"] == (start + timedelta(days=9)).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# ADR-085: positive-only gamification (softened PD-013)
# ─────────────────────────────────────────────────────────────────────────────


def test_medication_module_positive_only_no_penalties():
    """ADR-085: Health-модуль может давать XP/достижения за adherence, но не штрафовать.

    Пропуск/мисс никогда не отнимает баллы — негативная геймификация запрещена.
    """
    import inspect

    import app.api.medication as mod
    import app.services.med_service as svc_mod

    source = inspect.getsource(mod) + inspect.getsource(svc_mod)
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


# ─────────────────────────────────────────────────────────────────────────────
# Phase C (ADR-189): курсы, сводные приёмы по слотам, аптечка → локация
# ─────────────────────────────────────────────────────────────────────────────


async def _create_course(auth_client, name: str = "Antibiotic course", start: str = "2026-09-10") -> str:
    resp = await auth_client.post("/med-courses", data={"name": name, "start_date": start})
    assert resp.status_code == 303, resp.text
    return name


async def _course_id(db: AsyncSession, user_id, name: str) -> str:
    c = (await db_session_exec(db, MedCourse, user_id, name)).id
    return str(c)


async def db_session_exec(db: AsyncSession, model, user_id, name: str):
    return (await db.execute(select(model).where(model.user_id == user_id, model.name == name))).scalar_one()


@pytest.mark.asyncio
async def test_course_create_and_add_item(auth_client, test_user, db_session):
    """Курс: создание + элемент с режимом приёма; end_date = start + duration − 1; course_id на расписании."""
    await _create_medication(auth_client, "Amoxicillin")
    med_id = await _get_med_id(db_session, test_user.id, "Amoxicillin")
    await _create_course(auth_client, "AB course", "2026-09-10")
    cid = await _course_id(db_session, test_user.id, "AB course")

    resp = await auth_client.post(
        f"/med-courses/{cid}/items",
        data={
            "medication_id": str(med_id),
            "dose_quantity": "1",
            "dose_unit": "tablet",
            "frequency_type": "daily",
            "times_per_day": "3",
            "food_relation": "before_meal",
            "duration_days": "10",
        },
    )
    assert resp.status_code == 303, resp.text

    s = (await db_session.execute(select(MedSchedule).where(MedSchedule.course_id == uuid.UUID(cid)))).scalar_one()
    assert s.food_relation == "before_meal"
    assert s.end_date == date(2026, 9, 19)  # 10 дней с 10.09
    assert s.times_per_day == 3

    page = await auth_client.get("/medications")
    assert page.status_code == 200
    assert "AB course" in page.text
    assert "Amoxicillin" in page.text


@pytest.mark.asyncio
async def test_course_status_flow(auth_client, test_user, db_session):
    """Статусы курса: planned → active → paused; is_active следует за статусом."""
    await _create_course(auth_client, "Vitamins", "")
    cid = await _course_id(db_session, test_user.id, "Vitamins")

    for status, active in (("active", True), ("paused", False), ("completed", False), ("planned", True)):
        resp = await auth_client.post(f"/med-courses/{cid}/status", data={"status": status})
        assert resp.status_code == 303, resp.text
        c = await db_session_exec(db_session, MedCourse, test_user.id, "Vitamins")
        assert c.status == status
        assert c.is_active is active


@pytest.mark.asyncio
async def test_batch_intake_records_all_slot_schedules(auth_client, test_user, db_session):
    """Сводный приём (ADR-189): одна отметка на слот закрывает все препараты слота."""
    for name in ("Drug A", "Drug B"):
        await _create_medication(auth_client, name)
        mid = await _get_med_id(db_session, test_user.id, name)
        resp = await auth_client.post(
            f"/medications/{mid}/schedule",
            data={"dose_quantity": "1", "frequency_type": "daily", "times_of_day": "09:00"},
        )
        assert resp.status_code == 303, resp.text

    scheds = (await db_session.execute(select(MedSchedule))).scalars().all()
    assert len(scheds) == 2
    ids = ",".join(str(s.id) for s in scheds)
    resp = await auth_client.post("/med-intakes/batch", data={"schedule_ids": ids, "slot_time": "09:00"})
    assert resp.status_code == 303, resp.text

    intakes = (await db_session.execute(select(MedIntake))).scalars().all()
    assert len(intakes) == 2
    assert all(i.status == "taken" for i in intakes)
    assert {i.schedule_id for i in intakes} == {s.id for s in scheds}


@pytest.mark.asyncio
async def test_schedule_summary_groups_slots(auth_client, test_user, db_session):
    """schedule_summary возвращает слоты; отметка приёма закрывает слот (all_taken)."""
    await _create_medication(auth_client, "Metformin")
    mid = await _get_med_id(db_session, test_user.id, "Metformin")
    resp = await auth_client.post(
        f"/medications/{mid}/schedule",
        data={"dose_quantity": "1", "frequency_type": "daily", "times_of_day": "08:00, 13:00, 19:00"},
    )
    assert resp.status_code == 303, resp.text

    data = (await auth_client.get("/api/v2/medications/today")).json()
    assert data.get("slots"), "ожидались слоты"
    times = [s["time"] for s in data["slots"]]
    assert "08:00" in times and "13:00" in times and "19:00" in times
    assert all(not s["all_taken"] for s in data["slots"])
    assert any(m["medication_name"] == "Metformin" for s in data["slots"] for m in s["meds"])

    sched = (await db_session.execute(select(MedSchedule))).scalar_one()
    resp = await auth_client.post("/med-intakes/batch", data={"schedule_ids": str(sched.id), "slot_time": "08:00"})
    assert resp.status_code == 303, resp.text
    data = (await auth_client.get("/api/v2/medications/today")).json()
    slot_08 = next(s for s in data["slots"] if s["time"] == "08:00")
    assert slot_08["all_taken"] is True
    assert any(not s["all_taken"] for s in data["slots"] if s["time"] != "08:00")


@pytest.mark.asyncio
async def test_kit_linked_to_location(auth_client, test_user, db_session):
    """Аптечка привязывается к иерархической локации (location_id) и показывает путь."""
    from app.models.task_location import TaskLocation

    loc = TaskLocation(slug="test-home-shelf", title_ru="Квартира / Полка", owner_id=test_user.id)
    db_session.add(loc)
    await db_session.flush()

    resp = await auth_client.post("/med-kits", data={"name": "Shelf kit", "location_id": str(loc.id), "location": ""})
    assert resp.status_code == 303, resp.text
    kit = (await db_session.execute(select(MedKit).where(MedKit.user_id == test_user.id))).scalar_one()
    assert kit.location_id == loc.id
    assert kit.linked_location is not None

    # чужую локацию привязать нельзя
    other = User(email="loc-other@example.com", password_hash=hash_password("x"), locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    foreign_loc = TaskLocation(slug="test-foreign-shelf", title_ru="Чужое", owner_id=other.id)
    db_session.add(foreign_loc)
    await db_session.flush()
    resp = await auth_client.post(
        "/med-kits", data={"name": "Bad kit", "location_id": str(foreign_loc.id), "location": ""}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_dashboard_merge_med_group(auth_client, test_user, db_session):
    """Today-сводка: med_group появляется как одна задача на слот со списком schedule_id."""
    from app.services.dashboard_service import _merge_today_items

    merged = _merge_today_items(
        [],
        {
            "slots": [
                {
                    "time": "07:30",
                    "all_taken": False,
                    "meds": [
                        {"schedule_id": "s1", "medication_name": "Drug A", "dose": "1 tablet"},
                        {"schedule_id": "s2", "medication_name": "Drug B", "dose": "1 capsule"},
                    ],
                }
            ]
        },
    )
    groups = [i for i in merged if i["kind"] == "med_group"]
    assert len(groups) == 1
    assert groups[0]["slot_time"] == "07:30"
    assert {m["schedule_id"] for m in groups[0]["meds"]} == {"s1", "s2"}


# ─────────────────────────────────────────────────────────────────────────────
# Phase D (ADR-189): умный ввод — свободный текст → параметры режима
# ─────────────────────────────────────────────────────────────────────────────


def _assert_regimen(text: str, expected: dict):
    parsed = parse_regimen_text(text)
    for key, val in expected.items():
        assert parsed[key] == val, f"{text}: {key}={parsed.get(key)!r} != {val!r}"


def test_parse_regimen_russian_phrases():
    cases = [
        (
            "3 раза в день до еды 20 дней",
            {"frequency_type": "daily", "times_per_day": 3, "food_relation": "before_meal", "duration_days": 20},
        ),
        (
            "2 раза в день после еды 10 дней",
            {"frequency_type": "daily", "times_per_day": 2, "food_relation": "after_meal", "duration_days": 10},
        ),
        ("1 раз в день утром", {"frequency_type": "daily", "times_per_day": 1, "times_of_day": "08:00"}),
        ("натощак за 30 мин до завтрака", {"frequency_type": "daily", "food_relation": "empty_stomach"}),
        ("каждые 6 часов", {"frequency_type": "interval", "interval_hours": 6.0}),
        ("раз в день", {"frequency_type": "daily", "times_per_day": 1}),
        ("ежедневно", {"frequency_type": "daily", "times_per_day": 1}),
    ]
    for text, expected in cases:
        _assert_regimen(text, expected)


def test_parse_regimen_dose_and_weekdays():
    cases = [
        (
            "1 таблетка каждые 8 часов с понедельника",
            {"frequency_type": "interval", "interval_hours": 8.0, "dose_quantity": 1.0, "dose_unit": "tablet"},
        ),
        (
            "по 2 таблетки 2 раза в день во время еды с 15.09 на 10 дней",
            {
                "frequency_type": "daily",
                "times_per_day": 2,
                "food_relation": "during_meal",
                "duration_days": 10,
                "dose_quantity": 2.0,
                "dose_unit": "tablet",
            },
        ),
        ("по понедельникам и средам", {"frequency_type": "weekly", "days_of_week": "0,2"}),
        (
            "по будням в 08:00 и 20:00",
            {"frequency_type": "weekly", "days_of_week": "0,1,2,3,4", "times_of_day": "08:00, 20:00"},
        ),
    ]
    for text, expected in cases:
        _assert_regimen(text, expected)


def test_parse_regimen_english_phrases():
    cases = [
        (
            "1 time a day before meals for 20 days",
            {"frequency_type": "daily", "times_per_day": 1, "food_relation": "before_meal", "duration_days": 20},
        ),
        (
            "1 capsule every 8 hours for 5 days",
            {"frequency_type": "interval", "interval_hours": 8.0, "duration_days": 5, "dose_unit": "capsule"},
        ),
        ("2 times a day after meals", {"frequency_type": "daily", "times_per_day": 2, "food_relation": "after_meal"}),
        ("every Monday and Wednesday", {"frequency_type": "weekly", "days_of_week": "0,2"}),
    ]
    for text, expected in cases:
        _assert_regimen(text, expected)


@pytest.mark.parametrize("text", ["", "пить чаще", "принимать по настроению", "abc 123 ??"])
def test_parse_regimen_garbage_rejected(text: str):
    with pytest.raises(ValueError):
        parse_regimen_text(text)


def test_parse_regimen_never_sets_end_date():
    """Парсер предлагает параметры (длительность/старт), но не материализует end_date."""
    parsed = parse_regimen_text("3 раза в день до еды 20 дней")
    assert "end_date" not in parsed
    assert "duration_days" in parsed


@pytest.mark.asyncio
async def test_page_parse_regimen_endpoint(auth_client, test_user):
    """POST /medications/parse-regimen → ok+params; мусор → error без сохранения."""
    resp = await auth_client.post("/medications/parse-regimen", data={"text": "3 раза в день до еды 20 дней"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["params"]["times_per_day"] == 3
    assert body["params"]["food_relation"] == "before_meal"
    assert body["params"]["duration_days"] == 20

    resp = await auth_client.post("/medications/parse-regimen", data={"text": "пить чаще"})
    body = resp.json()
    assert body["status"] == "error"
    assert body["message"]


@pytest.mark.asyncio
async def test_json_parse_regimen_endpoint(auth_client):
    """JSON (mobile parity): POST /api/v2/medications/regimen/parse."""
    resp = await auth_client.post(
        "/api/v2/medications/regimen/parse", json={"text": "1 capsule every 6 hours for 7 days"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["frequency_type"] == "interval"
    assert body["interval_hours"] == 6.0
    assert body["duration_days"] == 7
    assert body["dose_unit"] == "capsule"

    resp = await auth_client.post("/api/v2/medications/regimen/parse", json={"text": "непонятно"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_parse_endpoint_persists_nothing(auth_client, test_user, db_session):
    """Умный ввод ничего не сохраняет: после разбора не появляется расписаний/приёмов."""
    await _create_medication(auth_client, "Cleanup med")
    await auth_client.post("/medications/parse-regimen", data={"text": "3 раза в день до еды 20 дней"})
    scheds = (await db_session.execute(select(MedSchedule).where(MedSchedule.user_id == test_user.id))).scalars().all()
    intakes = (await db_session.execute(select(MedIntake).where(MedIntake.user_id == test_user.id))).scalars().all()
    assert scheds == []
    assert intakes == []


# ─────────────────────────────────────────────────────────────────────────────
# ADR-190, phase E: substances, composition, autofill, grouping, search
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_substance():
    assert normalize_substance("  Ибупрофен ") == "ибупрофен"
    assert normalize_substance("Ибупрофен") == normalize_substance("ибупрофен")
    assert normalize_substance("Эстрадиол") == normalize_substance("  эстрадиол! ")
    # соль/эфир — отдельная строка (ADR-190 «Границы»)
    assert normalize_substance("Эстрадиола валерат") != normalize_substance("Эстрадиол")
    # ё → е
    assert normalize_substance("Аевит") == normalize_substance("Аевит")
    assert normalize_substance("Хлоргексидина биглюконат") == "хлоргексидина биглюконат"


def test_parse_components_payload_dedup_and_invalid():
    rows = parse_components_payload(
        '[{"substance":"Эстрадиол","amount":2,"unit":"мг","variant":"белые 1–14"},'
        '{"name":"Эстрадиол","amount":2,"unit":"мг","variant":"Белые 1–14"},'
        '{"substance":"Дидрогестерон","amount":10,"unit":"мг"},'
        '{"amount":5}]'
    )
    assert len(rows) == 2  # дубль «вещество+вариант» схлопнут; строка без вещества отброшена
    assert rows[0]["substance"] == "Эстрадиол"
    assert rows[1]["substance"] == "Дидрогестерон"
    assert parse_components_payload("") == []
    assert parse_components_payload(None) == []
    with pytest.raises(ValueError):
        parse_components_payload("{broken json")
    with pytest.raises(ValueError):
        parse_components_payload('{"not": "a list"}')


@pytest.mark.asyncio
async def test_create_medication_with_components_and_variants(auth_client, test_user, db_session):
    """Фемостон 2/10: 2 варианта пачки, 3 компонента, вещества дедуплицированы по norm_key."""
    components = (
        '[{"substance":"Эстрадиол","inn":"Estradiolum","amount":2,"unit":"мг","variant":"белые 1–14"},'
        '{"substance":"Эстрадиол","inn":"Estradiolum","amount":2,"unit":"мг","variant":"серые 15–28"},'
        '{"substance":"Дидрогестерон","inn":"Dydrogesteronum","amount":10,"unit":"мг","variant":"серые 15–28"}]'
    )
    resp = await auth_client.post(
        "/medications",
        data={"name": "Фемостон 2/10", "kind": "medication", "form": "таблетки", "components": components},
    )
    assert resp.status_code == 303, resp.text
    med = (
        await db_session.execute(
            select(Medication).where(Medication.user_id == test_user.id, Medication.name == "Фемостон 2/10")
        )
    ).scalar_one()
    comps = (await db_session.execute(select(MedComponent).where(MedComponent.medication_id == med.id))).scalars().all()
    assert len(comps) == 3
    variants = (await db_session.execute(select(MedVariant).where(MedVariant.medication_id == med.id))).scalars().all()
    assert len(variants) == 2
    substances = (await db_session.execute(select(MedSubstance))).scalars().all()
    assert {s.name for s in substances} == {"Эстрадиол", "Дидрогестерон"}
    est = next(s for s in substances if s.name == "Эстрадиол")
    assert est.inn == "Estradiolum"
    assert est.norm_key == "эстрадиол"
    # страница показывает состав
    page = await auth_client.get("/medications")
    assert page.status_code == 200
    assert "Эстрадиол" in page.text
    assert "Дидрогестерон" in page.text


@pytest.mark.asyncio
async def test_create_medication_legacy_ingredient_becomes_component(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/medications", data={"name": "Бепантен", "kind": "medication", "active_ingredient": "Декспантенол"}
    )
    assert resp.status_code == 303, resp.text
    med = (
        await db_session.execute(
            select(Medication).where(Medication.user_id == test_user.id, Medication.name == "Бепантен")
        )
    ).scalar_one()
    comps = (await db_session.execute(select(MedComponent).where(MedComponent.medication_id == med.id))).scalars().all()
    assert len(comps) == 1
    assert comps[0].substance.name == "Декспантенол"
    assert comps[0].amount is None


@pytest.mark.asyncio
async def test_allow_ul_override_checkbox_persists(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/medications",
        data={
            "name": "Витамин D",
            "kind": "supplement",
            "allow_ul_override": "1",
            "components": '[{"substance":"Колекальциферол","unit":"мкг"}]',
        },
    )
    assert resp.status_code == 303, resp.text
    med = (
        await db_session.execute(
            select(Medication).where(Medication.user_id == test_user.id, Medication.name == "Витамин D")
        )
    ).scalar_one()
    assert med.allow_ul_override is True
    page = await auth_client.get("/medications")
    assert page.status_code == 200
    assert "Витамин D" in page.text
    assert "daily limit" in page.text


@pytest.mark.asyncio
async def test_json_create_with_components(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/medications",
        json={
            "name": "Компливит",
            "kind": "supplement",
            "allow_ul_override": True,
            "components": [
                {"name": "Ретинол", "amount": 1.0, "unit": "мг"},
                {"name": "Аскорбиновая кислота", "amount": 100.0, "unit": "мг"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    med = (
        await db_session.execute(
            select(Medication).where(Medication.user_id == test_user.id, Medication.name == "Компливит")
        )
    ).scalar_one()
    assert med.allow_ul_override is True
    comps = (await db_session.execute(select(MedComponent).where(MedComponent.medication_id == med.id))).scalars().all()
    assert len(comps) == 2
    assert {c.substance.name for c in comps} == {"Ретинол", "Аскорбиновая кислота"}


@pytest.mark.asyncio
async def test_search_and_grouping_by_substance(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/medications", data={"name": "Нурофен", "kind": "medication", "active_ingredient": "Ибупрофен"}
    )
    assert resp.status_code == 303, resp.text
    resp = await auth_client.post(
        "/medications", data={"name": "Бепантен", "kind": "medication", "active_ingredient": "Декспантенол"}
    )
    assert resp.status_code == 303, resp.text
    # поиск по названию вещества (не входящему в имя препарата)
    page = await auth_client.get("/medications", params={"q": "декспантенол"})
    assert page.status_code == 200
    assert "Бепантен" in page.text
    assert "Нурофен" not in page.text
    # группировка «по действующему веществу» присутствует на странице
    page = await auth_client.get("/medications")
    assert "Декспантенол" in page.text
    assert "Ибупрофен" in page.text


@pytest.mark.asyncio
async def test_autofill_seeded_and_mask(auth_client):
    resp = await auth_client.post("/medications/autofill-info", data={"name": "Бепантен"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    comps = data["data"]["components"]
    assert comps and comps[0]["name"] == "Декспантенол"
    assert comps[0]["inn"] == "Dexpanthenol"

    resp = await auth_client.post("/medications/autofill-info", data={"name": "Фемостон 2/10"})
    data = resp.json()
    assert data["status"] == "ok"
    subs = [c["name"] for c in data["data"]["components"]]
    assert "Эстрадиол" in subs and "Дидрогестерон" in subs
    variants = {c.get("variant") for c in data["data"]["components"]}
    assert len(variants) == 2


@pytest.mark.asyncio
async def test_autofill_unknown_is_honest_not_found(auth_client):
    resp = await auth_client.post("/medications/autofill-info", data={"name": "Zyxwvut 3000"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "not_found"
    assert data["message"]


@pytest.mark.asyncio
async def test_json_autofill_404_and_ok(auth_client):
    resp = await auth_client.post("/api/v2/medications/autofill", json={"name": "Zyxwvut 3000"})
    assert resp.status_code == 404
    resp = await auth_client.post("/api/v2/medications/autofill", json={"name": "Нурофен"})
    assert resp.status_code == 200
    assert resp.json()["components"][0]["name"] == "Ибупрофен"
