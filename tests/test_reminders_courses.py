"""Reminders + procedure courses + cycle insights tests (Шаг 17c, ADR-095).

Покрывает:
- reminder engine: сбор напоминаний (лекарства/средства/уход/курсы) и
  дедупликацию через reminder_log;
- курсы процедур (care_courses / care_course_sessions): CRUD, прогресс,
  next-session reminder;
- авто-инсайты: run_auto_insights для opted-in пользователей;
- cycle-раздел в контексте Insights.

Relief-only (PD-013): напоминания и курсы не применяют очки/штрафы.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.care import CareCourse, CareCourseSession, CareProduct, CareRoutine
from app.models.insights import InsightRun
from app.models.medication import Medication, MedSchedule
from app.models.notification import Notification
from app.models.reminder_log import ReminderLog
from app.models.user import User

TODAY = date.today()


async def _add_medication(db_session, user, name="Paracetamol"):
    med = Medication(user_id=user.id, name=name, kind="medication")
    db_session.add(med)
    await db_session.flush()
    return med


# ─────────────────────────────────────────────────────────────────────────────
# Reminder engine — collectors + dedupe
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_medication_due_reminder_and_dedupe(db_session, test_user):
    from datetime import UTC, datetime

    from app.reminders.engine import collect_reminders, deliver_reminders

    med = await _add_medication(db_session, test_user)
    db_session.add(
        MedSchedule(
            user_id=test_user.id,
            medication_id=med.id,
            dose_quantity=1,
            frequency_type="daily",
            times_per_day=2,
            is_active=True,
        )
    )
    await db_session.flush()

    reminders = await collect_reminders(db_session, test_user.id, TODAY, datetime.now(UTC))
    due = [r for r in reminders if r.kind == "med_due"]
    assert len(due) == 1

    delivered = await deliver_reminders(db_session, test_user, reminders)
    assert delivered == 1
    # второй вызов — дедупликация: ничего нового
    delivered2 = await deliver_reminders(db_session, test_user, reminders)
    assert delivered2 == 0
    n = (
        await db_session.execute(select(Notification).where(Notification.user_id == test_user.id))
    ).scalars().all()
    assert len(n) == 1
    assert n[0].type == "reminder"


@pytest.mark.asyncio
async def test_care_product_low_stock_and_expiring(db_session, test_user):
    from datetime import UTC, datetime

    from app.reminders.engine import collect_reminders

    db_session.add(CareProduct(user_id=test_user.id, name="Serum", category="serum", quantity=1))
    db_session.add(
        CareProduct(
            user_id=test_user.id,
            name="Mask",
            category="mask",
            quantity=5,
            expiry_date=TODAY + timedelta(days=10),
        )
    )
    await db_session.flush()
    reminders = await collect_reminders(db_session, test_user.id, TODAY, datetime.now(UTC))
    kinds = {r.kind for r in reminders}
    assert "care_product_low" in kinds
    assert "care_product_expiring" in kinds


@pytest.mark.asyncio
async def test_care_routine_due(db_session, test_user):
    from datetime import UTC, datetime

    from app.reminders.engine import collect_reminders

    db_session.add(
        CareRoutine(user_id=test_user.id, name="Peeling", area="face", kind="home", frequency_days=7)
    )
    await db_session.flush()
    reminders = await collect_reminders(db_session, test_user.id, TODAY, datetime.now(UTC))
    assert any(r.kind == "care_routine_due" for r in reminders)


@pytest.mark.asyncio
async def test_reminder_cycle_runs_for_all_users(db_session, test_user):
    from app.reminders.engine import run_reminder_cycle

    med = await _add_medication(db_session, test_user)
    db_session.add(
        MedSchedule(
            user_id=test_user.id,
            medication_id=med.id,
            dose_quantity=1,
            frequency_type="daily",
            times_per_day=1,
            is_active=True,
        )
    )
    await db_session.flush()
    total = await run_reminder_cycle(db_session, tz_name="UTC")
    assert total >= 1
    logs = (
        await db_session.execute(select(ReminderLog).where(ReminderLog.user_id == test_user.id))
    ).scalars().all()
    assert len(logs) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Procedure courses (series)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_course_generates_sessions(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/care/courses",
        data={
            "name": "Laser epilation",
            "area": "body",
            "total_sessions": "4",
            "interval_days": "30",
            "start_date": TODAY.isoformat(),
        },
    )
    assert resp.status_code == 303, resp.text
    course = (
        await db_session.execute(select(CareCourse).where(CareCourse.user_id == test_user.id))
    ).scalar_one()
    assert course.total_sessions == 4
    sessions = (
        await db_session.execute(
            select(CareCourseSession).where(CareCourseSession.course_id == course.id)
        )
    ).scalars().all()
    assert len(sessions) == 4
    assert sorted(s.session_number for s in sessions) == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_course_sessions_progress_and_page(auth_client, test_user, db_session):
    await auth_client.post(
        "/care/courses",
        data={"name": "Massage course", "area": "body", "total_sessions": "3", "interval_days": "7"},
    )
    course = (
        await db_session.execute(select(CareCourse).where(CareCourse.user_id == test_user.id))
    ).scalar_one()
    session = (
        await db_session.execute(
            select(CareCourseSession)
            .where(CareCourseSession.course_id == course.id, CareCourseSession.session_number == 1)
        )
    ).scalar_one()
    resp = await auth_client.post(f"/care/course-sessions/{session.id}/done")
    assert resp.status_code == 303, resp.text
    await db_session.refresh(session)
    assert session.status == "done"

    resp = await auth_client.get("/care")
    assert resp.status_code == 200
    assert "Massage course" in resp.text


@pytest.mark.asyncio
async def test_course_next_session_reminder(db_session, test_user):
    from datetime import UTC, datetime

    from app.reminders.engine import collect_reminders

    course = CareCourse(user_id=test_user.id, name="Laser", area="body", total_sessions=3, interval_days=7)
    db_session.add(course)
    await db_session.flush()
    for i in range(1, 4):
        db_session.add(
            CareCourseSession(
                course_id=course.id,
                session_number=i,
                scheduled_date=TODAY + timedelta(days=(i - 1) * 7),
                status="pending",
            )
        )
    await db_session.flush()
    reminders = await collect_reminders(db_session, test_user.id, TODAY, datetime.now(UTC))
    assert any(r.kind == "care_course_session" for r in reminders)


@pytest.mark.asyncio
async def test_json_add_course(auth_client, test_user, db_session):
    resp = await auth_client.post(
        "/api/v2/care/courses",
        json={"name": "Laser", "area": "body", "total_sessions": 2, "interval_days": 30},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["total_sessions"] == 2
    assert len(data["sessions"]) == 2


@pytest.mark.asyncio
async def test_json_list_courses(auth_client, test_user, db_session):
    """GET /api/v2/care/courses returns the user's courses (mobile listing)."""
    # Create one course via JSON, another directly.
    await auth_client.post(
        "/api/v2/care/courses",
        json={"name": "Laser", "area": "body", "total_sessions": 2, "interval_days": 30},
    )
    course2 = CareCourse(user_id=test_user.id, name="Massage", area="body", total_sessions=1)
    db_session.add(course2)
    await db_session.flush()

    resp = await auth_client.get("/api/v2/care/courses")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    names = {c["name"] for c in data}
    assert names == {"Laser", "Massage"}
    # each course carries its sessions
    laser = next(c for c in data if c["name"] == "Laser")
    assert len(laser["sessions"]) == 2


@pytest.mark.asyncio
async def test_json_list_courses_cross_user_isolation(auth_client, test_user, db_session):
    """GET /api/v2/care/courses never leaks another user's courses."""
    other = User(email="other-courses@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    db_session.add(CareCourse(user_id=other.id, name="Other course", area="face"))
    await db_session.flush()

    resp = await auth_client.get("/api/v2/care/courses")
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == []


@pytest.mark.asyncio
async def test_json_delete_course(auth_client, test_user, db_session):
    """DELETE /api/v2/care/courses/{id} — mobile CRUD, sessions removed too."""
    resp = await auth_client.post(
        "/api/v2/care/courses",
        json={"name": "Laser", "area": "body", "total_sessions": 3, "interval_days": 7},
    )
    course_id = resp.json()["id"]

    del_resp = await auth_client.delete(f"/api/v2/care/courses/{course_id}")
    assert del_resp.status_code == 204, del_resp.text

    assert (await auth_client.get("/api/v2/care/courses")).json() == []


@pytest.mark.asyncio
async def test_json_delete_course_foreign_rejected(auth_client, test_user, db_session):
    other = User(email="other-course-del@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    course = CareCourse(user_id=other.id, name="Other", area="face")
    db_session.add(course)
    await db_session.flush()

    resp = await auth_client.delete(f"/api/v2/care/courses/{course.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_course_cross_user_isolation(auth_client, test_user, db_session):
    other = User(email="other2@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    course = CareCourse(user_id=other.id, name="Other course", area="face")
    db_session.add(course)
    await db_session.flush()
    # чужой курс недоступен через delete
    resp = await auth_client.post(f"/care/courses/{course.id}/delete")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Auto-run insights
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_insights_opted_in_only(db_session, test_user, monkeypatch):
    import json as _json

    from app.insights.scheduler import run_auto_insights
    from app.llm import client

    # пользователь без insights_auto → пропуск
    runs = await run_auto_insights(db_session)
    assert runs == 0

    # включить insights_auto + активный LLM-конфиг
    test_user.prefs = {"insights_auto": True, "insights_auto_days": 7}
    await _add_llm_config(db_session, test_user.id)

    async def fake_call_llm(config, system_prompt, user_message, tools=None, json_mode=True, images=None):
        return {
            "content": _json.dumps({"summary": "s", "findings": []}),
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0},
            "tool_calls": [],
        }

    monkeypatch.setattr(client, "call_llm", fake_call_llm)
    runs = await run_auto_insights(db_session)
    assert runs == 1
    stored = (
        await db_session.execute(select(InsightRun).where(InsightRun.user_id == test_user.id))
    ).scalars().all()
    assert len(stored) == 1


async def _add_llm_config(db_session, user_id):
    from app.models.llm_config import LLMProviderConfig

    cfg = LLMProviderConfig(
        user_id=user_id, provider_name="test", api_base_url="http://x/v1", model_name="m", is_active=True
    )
    db_session.add(cfg)
    await db_session.flush()
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Cycle insights context
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cycle_context_builder(db_session, test_user):
    from app.llm.pipeline.insights import _ctx_cycle
    from app.models.health import CycleEvent, CycleSettings, HealthState

    db_session.add(CycleSettings(user_id=test_user.id, cycle_length=28, period_length=5))
    db_session.add(CycleEvent(user_id=test_user.id, event_date=TODAY - timedelta(days=5), event_type="bleeding"))
    db_session.add(HealthState(user_id=test_user.id, event_date=TODAY, mood=4, energy=3, sleep_hours=7, recovery=4))
    await db_session.flush()

    lines = await _ctx_cycle(db_session, test_user.id, TODAY - timedelta(days=30), TODAY)
    assert lines, "cycle context should not be empty"
    assert any("cycle:" in line for line in lines)
    # настроение попало в какую-то фазу
    assert any("mood" in line for line in lines)


@pytest.mark.asyncio
async def test_cycle_section_in_insight_sections():
    from app.models.insights import INSIGHT_SECTIONS

    assert "cycle" in INSIGHT_SECTIONS


# ─────────────────────────────────────────────────────────────────────────────
# Relief-only: reminders never apply points/penalties
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reminders_relief_only(db_session, test_user):
    from datetime import UTC, datetime

    from app.reminders.engine import collect_reminders, deliver_reminders

    db_session.add(CareProduct(user_id=test_user.id, name="Serum", category="serum", quantity=1))
    await db_session.flush()
    reminders = await collect_reminders(db_session, test_user.id, TODAY, datetime.now(UTC))
    await deliver_reminders(db_session, test_user, reminders)
    # нет points_transactions / achievements — только Notification + ReminderLog
    n = (
        await db_session.execute(select(Notification).where(Notification.user_id == test_user.id))
    ).scalars().all()
    assert len(n) >= 1
    for item in n:
        assert item.type == "reminder"
