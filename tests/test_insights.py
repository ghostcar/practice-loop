"""Personal Insights tests (Шаг 17, ADR-093, ROADMAP §7 4E).

Явно запрошенный кросс-модульный LLM-анализ личных данных. Relief-only (PD-013):
без игровой интеграции; анализ показывает использованные данные и не объявляет
корреляцию причиной (промпт-ограничение); пользователь исключает разделы/период.
"""

from __future__ import annotations

import json as _json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.care import CareEntry
from app.models.health import HealthState
from app.models.insights import InsightFinding, InsightRun
from app.models.user import User

TODAY = date.today()


def _fake_llm(payload: dict):
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
        user_id=user_id, provider_name="test", api_base_url="http://x/v1", model_name="m", is_active=True
    )
    db_session.add(cfg)
    await db_session.flush()
    return cfg


def _findings_payload():
    return {
        "summary": "Overall trend: activity and sleep correlate.",
        "findings": [
            {
                "section": "tracker",
                "title": "High completion on good-sleep days",
                "summary": "Completed tasks tend to coincide with better sleep.",
                "used_data": ["completed: 5 (83%)", "avg sleep: 7.5 h"],
            },
            {
                "section": "care",
                "title": "Regular care routine",
                "summary": "Care entries were consistent across the period.",
                "used_data": ["care entries: 3"],
            },
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page + empty state
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insights_page_empty(auth_client, test_user, db_session):
    resp = await auth_client.get("/insights")
    assert resp.status_code == 200
    assert "insights_no_runs" in resp.text or "No analyses yet" in resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Context builder (unit)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_builder_filters_period_and_sections(test_user, db_session):
    from app.llm.pipeline.insights import build_insights_context

    # data inside period
    db_session.add(CareEntry(user_id=test_user.id, entry_date=TODAY, notes="in"))
    # data outside period (must be excluded)
    db_session.add(CareEntry(user_id=test_user.id, entry_date=TODAY - timedelta(days=400), notes="zzz-outside"))
    db_session.add(HealthState(user_id=test_user.id, event_date=TODAY, mood=4, energy=3, sleep_hours=7.5))
    await db_session.flush()

    start = TODAY - timedelta(days=30)
    ctx = await build_insights_context(db_session, test_user.id, ["care", "health"], start, TODAY)
    assert "care" in ctx
    assert "health" in ctx
    # только запись внутри периода (запись за 400 дней исключена)
    assert "care entries: 2" not in _json.dumps(ctx)
    assert "care entries: 1" in _json.dumps(ctx)

    # section not selected → not in context
    ctx2 = await build_insights_context(db_session, test_user.id, ["care"], start, TODAY)
    assert "health" not in ctx2


# ─────────────────────────────────────────────────────────────────────────────
# Run analysis
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_analysis_form(auth_client, test_user, db_session, monkeypatch):
    from app.llm import client

    monkeypatch.setattr(client, "call_llm", _fake_llm(_findings_payload()))
    await _setup_llm_config(db_session, test_user.id)
    db_session.add(CareEntry(user_id=test_user.id, entry_date=TODAY))
    await db_session.flush()

    resp = await auth_client.post(
        "/insights/run",
        data={
            "period_start": (TODAY - timedelta(days=30)).isoformat(),
            "period_end": TODAY.isoformat(),
            "sections": ["care", "tracker"],
        },
    )
    assert resp.status_code == 303, resp.text
    assert "run_id=" in resp.headers["location"]

    run = (await db_session.execute(select(InsightRun).where(InsightRun.user_id == test_user.id))).scalar_one()
    assert run.status == "completed"
    assert run.sections == ["care", "tracker"]
    assert run.usage_tokens == 15
    assert run.period_start == TODAY - timedelta(days=30)
    run_id = run.id

    resp = await auth_client.get(f"/insights?run_id={run_id}")
    assert resp.status_code == 200
    assert "High completion on good-sleep days" in resp.text
    assert "completed: 5 (83%)" in resp.text  # used_data transparent


@pytest.mark.asyncio
async def test_run_analysis_no_llm_config(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/insights/run",
        data={"period_start": TODAY.isoformat(), "period_end": TODAY.isoformat()},
    )
    assert resp.status_code == 303
    assert "error=no_llm_config" in resp.headers["location"]


@pytest.mark.asyncio
async def test_run_analysis_llm_failure_marks_failed(auth_client, test_user, db_session, monkeypatch):
    from app.llm import client

    async def failing_llm(config, system_prompt, user_message, tools=None, json_mode=True, images=None):
        raise ValueError("boom")

    monkeypatch.setattr(client, "call_llm", failing_llm)
    await _setup_llm_config(db_session, test_user.id)
    db_session.add(CareEntry(user_id=test_user.id, entry_date=TODAY))
    await db_session.flush()

    resp = await auth_client.post(
        "/insights/run", data={"period_start": TODAY.isoformat(), "period_end": TODAY.isoformat()}
    )
    assert resp.status_code == 303, resp.text
    run = (await db_session.execute(select(InsightRun).where(InsightRun.user_id == test_user.id))).scalar_one()
    assert run.status == "failed"
    assert "boom" in (run.error or "")


# ─────────────────────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_run_analysis(auth_client, test_user, db_session, monkeypatch):
    from app.llm import client

    monkeypatch.setattr(client, "call_llm", _fake_llm(_findings_payload()))
    await _setup_llm_config(db_session, test_user.id)
    db_session.add(CareEntry(user_id=test_user.id, entry_date=TODAY))
    await db_session.flush()

    resp = await auth_client.post(
        "/api/v2/insights",
        json={
            "period_start": (TODAY - timedelta(days=30)).isoformat(),
            "period_end": TODAY.isoformat(),
            "sections": ["care"],
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "completed"
    assert len(data["findings"]) == 2
    assert data["findings"][0]["section"] == "tracker"
    assert data["findings"][0]["used_data"]

    resp = await auth_client.get("/api/v2/insights")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    run_id = data["id"]
    resp = await auth_client.get(f"/api/v2/insights/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["summary"] == "Overall trend: activity and sleep correlate."


@pytest.mark.asyncio
async def test_json_run_no_llm_config(auth_client, test_user, db_session):
    resp = await auth_client.post("/api/v2/insights", json={"sections": ["care"]})
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Delete run (findings cascade)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_run_cascades_findings(auth_client, test_user, db_session, monkeypatch):
    from app.llm import client

    monkeypatch.setattr(client, "call_llm", _fake_llm(_findings_payload()))
    await _setup_llm_config(db_session, test_user.id)
    db_session.add(CareEntry(user_id=test_user.id, entry_date=TODAY))
    await db_session.flush()

    await auth_client.post("/insights/run", data={"period_start": TODAY.isoformat(), "period_end": TODAY.isoformat()})
    run = (await db_session.execute(select(InsightRun).where(InsightRun.user_id == test_user.id))).scalar_one()
    findings = (
        await db_session.execute(select(InsightFinding).where(InsightFinding.run_id == run.id))
    ).scalars().all()
    assert len(findings) == 2

    resp = await auth_client.post(f"/insights/runs/{run.id}/delete")
    assert resp.status_code == 303
    remaining = (
        await db_session.execute(select(InsightFinding).where(InsightFinding.run_id == run.id))
    ).scalars().all()
    assert len(remaining) == 0  # CASCADE


# ─────────────────────────────────────────────────────────────────────────────
# Cross-user isolation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_user_isolation(auth_client, test_user, db_session, monkeypatch):

    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    other_run = InsightRun(
        user_id=other.id, period_start=TODAY, period_end=TODAY, sections=["care"], status="completed"
    )
    db_session.add(other_run)
    await db_session.flush()
    db_session.add(
        InsightFinding(run_id=other_run.id, section="care", title="secret", summary="private")
    )
    await db_session.flush()

    resp = await auth_client.get("/api/v2/insights")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    resp = await auth_client.get(f"/api/v2/insights/runs/{other_run.id}")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard block
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_insights_block(auth_client, test_user, db_session, monkeypatch):
    from app.llm import client

    monkeypatch.setattr(client, "call_llm", _fake_llm(_findings_payload()))
    await _setup_llm_config(db_session, test_user.id)
    db_session.add(CareEntry(user_id=test_user.id, entry_date=TODAY))
    await db_session.flush()
    await auth_client.post("/insights/run", data={"period_start": TODAY.isoformat(), "period_end": TODAY.isoformat()})

    resp = await auth_client.get("/dashboard")
    assert resp.status_code == 200
    assert 'id="dash-block-insights"' in resp.text
    assert "dash_insights_runs" in resp.text or "analyses" in resp.text


# ─────────────────────────────────────────────────────────────────────────────
# Relief-only boundary (PD-013)
# ─────────────────────────────────────────────────────────────────────────────


def test_insights_module_no_gamification():
    """PD-013: инсайты не применяют игровую механику (по импортам и вызовам)."""
    import inspect

    import app.api.insights as mod
    import app.llm.pipeline.insights as pipeline
    import app.models.insights as models

    for source in (inspect.getsource(mod), inspect.getsource(pipeline), inspect.getsource(models)):
        assert "app.gamification" not in source
        assert "app.models.points" not in source
        assert "app.models.progress" not in source
        assert "award_points" not in source
        assert "apply_penalty" not in source
        assert "calculate_entity_penalty" not in source
