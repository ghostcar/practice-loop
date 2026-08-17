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
    """PD-013: Health-модуль не применяет игровую механику.

    Проверяем по импортам и вызовам игровых модулей/функций, а не по подстрокам
    (слово "expanded" из ADR-087 содержит "xp").
    """
    import inspect

    import app.api.health as mod

    source = inspect.getsource(mod)
    # no imports from gamification / points / progress domains
    assert "app.gamification" not in source
    assert "app.models.points" not in source
    assert "app.models.progress" not in source
    # no reward/penalty calls
    assert "award_points" not in source
    assert "on_medication_taken" not in source
    assert "apply_penalty" not in source
    assert "calculate_entity_penalty" not in source


# ─────────────────────────────────────────────────────────────────────────────
# LLM mode pref (ADR-087)
# ─────────────────────────────────────────────────────────────────────────────


def test_prefs_llm_mode_default_safe():
    from app.prefs import UserPrefs, sanitize_prefs

    assert UserPrefs().llm_mode == "safe"
    assert sanitize_prefs({})["llm_mode"] == "safe"
    assert sanitize_prefs({"llm_mode": "expanded"})["llm_mode"] == "expanded"
    assert sanitize_prefs({"llm_mode": "bogus"})["llm_mode"] == "safe"


@pytest.mark.asyncio
async def test_settings_save_llm_mode(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/settings",
        data={"llm_mode": "expanded", "theme_choice": "dark", "accent": "ember", "density": "comfortable"},
    )
    assert resp.status_code == 303, resp.text
    from app.prefs import prefs_from_dict

    # same session/identity map — the handler mutated user.prefs in place
    assert prefs_from_dict(test_user.prefs).llm_mode == "expanded"


# ─────────────────────────────────────────────────────────────────────────────
# LLM lab analysis (ADR-087)
# ─────────────────────────────────────────────────────────────────────────────


def _fake_llm(payload: dict):
    import json as _json

    async def fake_call_llm(config, system_prompt, user_message, tools=None, json_mode=True, images=None):
        return {
            "content": _json.dumps(payload),
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.001},
            "tool_calls": [],
        }

    return fake_call_llm


async def _setup_llm_config(db_session, user_id):
    from app.models.llm_config import LLMProviderConfig

    cfg = LLMProviderConfig(
        user_id=user_id,
        provider_name="test",
        api_base_url="http://x/v1",
        model_name="m",
        is_active=True,
    )
    db_session.add(cfg)
    await db_session.flush()
    return cfg


@pytest.mark.asyncio
async def test_analyze_labs_json_safe(auth_client, test_user, db_session, monkeypatch):
    from app.llm import client

    await auth_client.post(
        "/health/labs",
        data={
            "name": "Hemoglobin",
            "measured_at": TODAY.isoformat(),
            "value": "150",
            "unit": "g/L",
            "ref_range": "120-160",
        },
    )
    await _setup_llm_config(db_session, test_user.id)
    monkeypatch.setattr(
        client,
        "call_llm",
        _fake_llm(
            {
                "summary": "Hemoglobin 150 in range.",
                "observations": ["Hemoglobin 150 (ref 120-160)"],
                "assumptions": [],
                "questions_for_doctor": ["Ask about iron."],
            }
        ),
    )
    resp = await auth_client.post("/api/v2/health/analyze")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "safe"  # default prefs
    assert data["summary"] == "Hemoglobin 150 in range."
    assert data["questions_for_doctor"] == ["Ask about iron."]
    assert "recommendations" in data
    assert data["recommendations"] == []


@pytest.mark.asyncio
async def test_analyze_labs_json_expanded_includes_recommendations(
    auth_client, test_user, db_session, monkeypatch
):
    from app.llm import client

    # enable expanded mode + a medication schedule for dosing context
    await auth_client.post(
        "/settings",
        data={"llm_mode": "expanded", "theme_choice": "dark", "accent": "ember", "density": "comfortable"},
    )
    await auth_client.post(
        "/health/labs",
        data={"name": "Iron", "measured_at": TODAY.isoformat(), "value": "9", "unit": "µmol/L", "ref_range": "10-30"},
    )
    await _setup_llm_config(db_session, test_user.id)
    monkeypatch.setattr(
        client,
        "call_llm",
        _fake_llm(
            {
                "summary": "Iron slightly below range.",
                "observations": ["Iron 9 (ref 10-30)"],
                "assumptions": ["Single reading"],
                "questions_for_doctor": ["Ask about supplementation"],
                "recommendations": ["Discuss iron with your doctor"],
            }
        ),
    )
    resp = await auth_client.post("/api/v2/health/analyze")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "expanded"
    assert data["recommendations"] == ["Discuss iron with your doctor"]


@pytest.mark.asyncio
async def test_analyze_labs_form_redirect(auth_client, test_user, db_session, monkeypatch):
    """Form POST /health/analyze redirects to /health with the result in query."""
    from app.llm import client

    await auth_client.post(
        "/health/labs",
        data={"name": "TSH", "measured_at": TODAY.isoformat(), "value": "2.4", "unit": "mIU/L"},
    )
    await _setup_llm_config(db_session, test_user.id)
    monkeypatch.setattr(
        client,
        "call_llm",
        _fake_llm(
            {
                "summary": "TSH 2.4.",
                "observations": ["TSH 2.4"],
                "assumptions": [],
                "questions_for_doctor": [],
            }
        ),
    )
    resp = await auth_client.post("/health/analyze")
    assert resp.status_code == 303, resp.text
    assert resp.headers["location"].startswith("/health?analysis=")


@pytest.mark.asyncio
async def test_analyze_no_llm_config(auth_client, test_user, db_session):
    resp = await auth_client.post("/api/v2/health/analyze")
    assert resp.status_code == 400
    resp = await auth_client.post("/health/analyze")
    assert resp.status_code == 303
    assert "no_llm_config" in resp.headers["location"]


# ─────────────────────────────────────────────────────────────────────────────
# LLM mode hint across all blocks (ADR-087, Session 137)
# ─────────────────────────────────────────────────────────────────────────────


def test_llm_mode_hint_safe_and_expanded():
    from app.llm.mode import EXPANDED_HINT, SAFE_HINT, llm_mode_hint

    safe = llm_mode_hint("safe")
    expanded = llm_mode_hint("expanded")
    assert safe == SAFE_HINT
    assert expanded == EXPANDED_HINT
    assert safe != expanded
    # safe: factual, no unsolicited advice
    assert "factual" in safe
    assert "advice" in safe
    # expanded: recommendations allowed
    assert "recommendations" in expanded
    assert "advice" in expanded


def test_llm_mode_hint_defaults_to_prefs():
    """No explicit mode → reads from request-scoped prefs (safe by default)."""
    from app.llm.mode import llm_mode_hint
    from app.prefs import UserPrefs, reset_prefs, set_prefs

    # default (no prefs context) → safe
    assert llm_mode_hint() == llm_mode_hint("safe")

    token = set_prefs(UserPrefs(llm_mode="expanded"))
    try:
        assert llm_mode_hint() == llm_mode_hint("expanded")
    finally:
        reset_prefs(token)


def test_prompts_have_no_doctor_disclaimer():
    """Session 137: 'not a doctor' disclaimer lives in the UI, not in prompts."""
    import inspect
    import re

    import app.llm.health_prompts as hp

    # only the actual prompt strings (module docstring may mention the policy)
    source = inspect.getsource(hp)
    # strip the module docstring (first triple-quoted block)
    body = re.sub(r'^\s*""".*?"""\n', "", source, count=1, flags=re.DOTALL)
    assert "not a doctor" not in body.lower()
    assert "you are not" not in body.lower()


def test_pipeline_functions_accept_llm_mode():
    """All LLM pipeline functions expose the llm_mode parameter (None → prefs)."""
    import inspect

    from app.llm.pipeline import (
        analyze_diet_training_synergy,
        analyze_labs,
        analyze_training_day,
        evaluate_diet,
        generate_daily_plan,
        generate_diet,
        generate_from_template,
        generate_task,
        generate_weekly_tasks,
    )

    for fn in (
        generate_task,
        generate_weekly_tasks,
        generate_daily_plan,
        analyze_training_day,
        generate_diet,
        evaluate_diet,
        analyze_diet_training_synergy,
        analyze_labs,
        generate_from_template,
    ):
        sig = inspect.signature(fn)
        assert "llm_mode" in sig.parameters, f"{fn.__name__} missing llm_mode"
