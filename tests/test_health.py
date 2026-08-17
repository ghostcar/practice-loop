"""Health + Cycle foundation tests (M3 Personal Suite, Шаг 13, ROADMAP §7 4D).

Relief-only: Health-модуль без игровой интеграции (PD-013). Расчётная фаза
Cycle никогда не выдаётся за достоверный факт (PRODUCT_OVERVIEW §9.4).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.api.health import _cycle_phase, _day_of_cycle
from app.models.health import CycleEvent, CycleSettings, HealthState, LabRecord
from app.models.user import User

TODAY = date.today()


# ─────────────────────────────────────────────────────────────────────────────
# Page + check-in
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_page_empty(auth_client, test_user, db_session):
    resp = await auth_client.get("/health")
    assert resp.status_code == 200
    assert "dash-health" not in resp.text  # no dashboard block here
    assert "health_no_states" in resp.text or "No check-ins" in resp.text


@pytest.mark.asyncio
async def test_save_state_and_list(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/health/state",
        data={
            "event_date": TODAY.isoformat(),
            "mood": "4",
            "energy": "3",
            "sleep_hours": "7.5",
            "sleep_quality": "4",
            "recovery": "5",
            "symptoms": "headache, fatigue",
            "notes": "ok",
        },
    )
    assert resp.status_code == 303, resp.text
    states = (await db_session.execute(select(HealthState).where(HealthState.user_id == test_user.id))).scalars().all()
    assert len(states) == 1
    assert states[0].mood == 4
    assert states[0].symptoms == ["headache", "fatigue"]
    assert states[0].sleep_hours == 7.5

    # page shows it
    resp = await auth_client.get("/health")
    assert resp.status_code == 200
    assert "headache" in resp.text


@pytest.mark.asyncio
async def test_save_state_upsert_same_date(auth_client, test_user, db_session):
    await auth_client.post("/health/state", data={"event_date": TODAY.isoformat(), "mood": "2"})
    await auth_client.post("/health/state", data={"event_date": TODAY.isoformat(), "mood": "5"})
    states = (await db_session.execute(select(HealthState).where(HealthState.user_id == test_user.id))).scalars().all()
    assert len(states) == 1
    assert states[0].mood == 5


@pytest.mark.asyncio
async def test_invalid_mood_rejected(auth_client, test_user, db_session):
    resp = await auth_client.post("/health/state", data={"event_date": TODAY.isoformat(), "mood": "9"})
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Labs
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_lab_and_list(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/health/labs",
        data={
            "name": "Hemoglobin",
            "measured_at": TODAY.isoformat(),
            "value": "150",
            "unit": "g/L",
            "ref_range": "120-160",
            "lab_name": "LabX",
            "flagged": "1",
            "notes": "annual",
        },
    )
    assert resp.status_code == 303, resp.text
    recs = (await db_session.execute(select(LabRecord).where(LabRecord.user_id == test_user.id))).scalars().all()
    assert len(recs) == 1
    assert recs[0].name == "Hemoglobin"
    assert recs[0].ref_min == 120
    assert recs[0].ref_max == 160
    assert recs[0].flagged is True

    resp = await auth_client.get("/health")
    assert resp.status_code == 200
    assert "Hemoglobin" in resp.text


@pytest.mark.asyncio
async def test_lab_out_of_range_marker(auth_client, test_user, db_session):
    await auth_client.post(
        "/health/labs",
        data={"name": "Iron", "measured_at": TODAY.isoformat(), "value": "200", "unit": "µg", "ref_range": "50-170"},
    )
    resp = await auth_client.get("/health")
    assert resp.status_code == 200
    # out_of_range computed → the danger marker text appears
    assert "health_out_of_range" in resp.text or "out of range" in resp.text


@pytest.mark.asyncio
async def test_delete_lab(auth_client, test_user, db_session):
    await auth_client.post(
        "/health/labs", data={"name": "Glucose", "measured_at": TODAY.isoformat(), "value": "5.2"}
    )
    rec = (await db_session.execute(select(LabRecord).where(LabRecord.user_id == test_user.id))).scalar_one()
    resp = await auth_client.post(f"/health/labs/{rec.id}/delete")
    assert resp.status_code == 303
    remaining = (await db_session.execute(select(LabRecord).where(LabRecord.user_id == test_user.id))).scalars().all()
    assert len(remaining) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Cycle
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cycle_settings_save(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/health/cycle/settings",
        data={"cycle_length": "30", "period_length": "6", "contraception": "hormonal"},
    )
    assert resp.status_code == 303, resp.text
    row = (await db_session.execute(select(CycleSettings).where(CycleSettings.user_id == test_user.id))).scalar_one()
    assert row.cycle_length == 30
    assert row.contraception == "hormonal"


@pytest.mark.asyncio
async def test_cycle_event_add_and_phase(auth_client, test_user, db_session):
    # bleeding 5 days ago → day of cycle = 6 → follicular (period 5, cycle 28)
    start = TODAY - timedelta(days=5)
    resp = await auth_client.post(
        "/health/cycle/events",
        data={"event_date": start.isoformat(), "event_type": "bleeding", "value": "medium"},
    )
    assert resp.status_code == 303, resp.text
    evs = (await db_session.execute(select(CycleEvent).where(CycleEvent.user_id == test_user.id))).scalars().all()
    assert len(evs) == 1
    assert evs[0].event_type == "bleeding"

    # JSON summary shows estimated phase
    resp = await auth_client.get("/api/v2/health/cycle")
    assert resp.status_code == 200
    data = resp.json()
    assert data["phase"] == "follicular"
    assert data["phase_estimated"] is True
    assert data["day_of_cycle"] == 6


@pytest.mark.asyncio
async def test_cycle_phase_unit():
    # day 2 → menstrual (period 5)
    assert _cycle_phase(2, 28, 5) == "menstrual"
    # day 6 → follicular
    assert _cycle_phase(6, 28, 5) == "follicular"
    # day 14 → ovulation
    assert _cycle_phase(14, 28, 5) == "ovulation"
    # day 20 → luteal
    assert _cycle_phase(20, 28, 5) == "luteal"


@pytest.mark.asyncio
async def test_day_of_cycle_no_data(auth_client, test_user, db_session):
    assert _day_of_cycle([], None, TODAY) is None


@pytest.mark.asyncio
async def test_day_of_cycle_restart_after_gap(auth_client, test_user, db_session):
    """Новый цикл начинается после перерыва ≥3 дней между кровотечениями."""
    evs = [
        CycleEvent(user_id=test_user.id, event_date=TODAY - timedelta(days=30), event_type="bleeding"),
        CycleEvent(user_id=test_user.id, event_date=TODAY - timedelta(days=26), event_type="bleeding"),
        CycleEvent(user_id=test_user.id, event_date=TODAY - timedelta(days=3), event_type="bleeding"),
    ]
    db_session.add_all(evs)
    await db_session.flush()
    # 3 days since last start → day 4 (cycle 28)
    assert _day_of_cycle(list(evs), None, TODAY) == 4


# ─────────────────────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_summary_and_state(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/health/state",
        json={"event_date": TODAY.isoformat(), "mood": 4, "energy": 3, "sleep_hours": 7.0},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mood"] == 4

    resp = await auth_client.get("/api/v2/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["today_state"]["mood"] == 4
    assert data["today"] == TODAY.isoformat()


@pytest.mark.asyncio
async def test_json_add_lab(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/health/labs",
        json={"name": "TSH", "measured_at": TODAY.isoformat(), "value": 2.4, "unit": "mIU/L", "ref_max": 4.2},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "TSH"


@pytest.mark.asyncio
async def test_json_add_cycle_event(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/health/cycle/events",
        json={"event_date": TODAY.isoformat(), "event_type": "libido", "value": "high"},
    )
    assert resp.status_code == 201, resp.text
    resp = await auth_client.get("/api/v2/health/cycle")
    assert any(e["event_type"] == "libido" for e in resp.json()["events"])


@pytest.mark.asyncio
async def test_json_invalid_cycle_event_type(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/health/cycle/events",
        json={"event_date": TODAY.isoformat(), "event_type": "bogus"},
    )
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Cross-user isolation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session):
    await auth_client.post(
        "/health/labs", data={"name": "Private Lab", "measured_at": TODAY.isoformat(), "value": "1"}
    )
    # second user
    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()

    import secrets

    from app.auth import create_access_token

    token = create_access_token(other.id)
    csrf = secrets.token_hex(32)
    auth_client.headers["Cookie"] = f"access_token={token}; csrf_token={csrf}"
    auth_client.headers["X-CSRF-Token"] = csrf

    resp = await auth_client.get("/api/v2/health/labs")
    assert resp.status_code == 200
    assert not any(rec["name"] == "Private Lab" for rec in resp.json())


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard block (Step 13)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_health_block_with_checkin(auth_client, test_user, db_session):
    await auth_client.post(
        "/health/state",
        data={"event_date": TODAY.isoformat(), "mood": "5", "symptoms": "none"},
    )
    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="dash-block-health"' in html


@pytest.mark.asyncio
async def test_dashboard_health_block_no_checkin(auth_client, test_user, db_session):
    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="dash-block-health"' in html
    assert "dash_health_checkin" in html or "No check-in yet" in html


# ─────────────────────────────────────────────────────────────────────────────
# Relief-only boundary (PD-013)
# ─────────────────────────────────────────────────────────────────────────────


def test_health_module_no_gamification():
    """PD-013: Health-модуль не импортирует и не применяет игровую механику."""
    import inspect

    import app.api.health as mod

    source = inspect.getsource(mod)
    assert "gamification" not in source
    assert "xp" not in source.lower()
    assert "penalty" not in source.lower()
    assert "points" not in source.lower()
