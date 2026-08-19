"""Tests for training feature: model, API, gamification integration."""

import json
import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification.handler import get_or_create_progress, on_task_completed
from app.llm.repair import JsonRepairError
from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.llm_config import LLMProviderConfig
from app.models.opt_in import UserEntityOptIn
from app.models.training import TrainingDay
from app.models.training_log import TrainingLogEntry

_USAGE = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0}


async def _make_active_config(db_session: AsyncSession, user_id) -> LLMProviderConfig:
    config = LLMProviderConfig(
        user_id=user_id,
        provider_name="TestProvider",
        api_base_url="http://test/v1",
        model_name="test-model",
        is_active=True,
    )
    db_session.add(config)
    await db_session.flush()
    return config


async def _make_allowed_entity(db_session: AsyncSession, user_id, owner_id=None) -> Entity:
    entity = Entity(
        type="one_time",
        real_name="Test Activity",
        category="test",
        owner_id=owner_id or user_id,
        is_public=False,
        # risk_level is informational metadata (ADR-106); opt-in is the approval
        risk_level="low",
        params_schema={"intensity": {"type": "integer", "min": 1, "max": 3}},
    )
    db_session.add(entity)
    await db_session.flush()
    opt_in = UserEntityOptIn(user_id=user_id, entity_id=entity.id, is_opted_in=True, desire_level="want")
    db_session.add(opt_in)
    await db_session.flush()
    return entity


async def _fake_llm(plan: dict):
    async def _call(**kwargs):
        return {"content": json.dumps(plan), "usage": _USAGE}

    return _call


# --- Model tests ---


@pytest.mark.asyncio
async def test_create_training_day(db_session: AsyncSession, test_user):
    """TrainingDay model can be created and persisted."""
    today = datetime.now(UTC).date()
    td = TrainingDay(
        user_id=test_user.id,
        target_date=today,
        status="planned",
    )
    db_session.add(td)
    await db_session.flush()

    assert td.id is not None
    assert td.status == "planned"
    assert td.target_date == today


@pytest.mark.asyncio
async def test_training_day_lifecycle(db_session: AsyncSession, test_user):
    """TrainingDay goes through planned → active → completed → analyzed."""
    td = TrainingDay(
        user_id=test_user.id,
        target_date=date.today(),
        status="planned",
    )
    db_session.add(td)
    await db_session.flush()

    td.status = "active"
    db_session.add(td)
    await db_session.flush()
    assert td.status == "active"

    td.status = "completed"
    db_session.add(td)
    await db_session.flush()
    assert td.status == "completed"

    td.status = "analyzed"
    td.analyzed_at = datetime.now(UTC)
    db_session.add(td)
    await db_session.flush()
    assert td.status == "analyzed"
    assert td.analyzed_at is not None


@pytest.mark.asyncio
async def test_activity_log_with_training(db_session: AsyncSession, test_user):
    """ActivityLog can link to TrainingDay and have subtasks."""
    today = date.today()
    td = TrainingDay(
        user_id=test_user.id,
        target_date=today,
        status="active",
    )
    db_session.add(td)
    await db_session.flush()

    subtasks = [
        {"id": 1, "desc": "Prepare", "is_done": True},
        {"id": 2, "desc": "Execute", "is_done": False},
        {"id": 3, "desc": "Clean up", "is_done": False},
    ]

    log = ActivityLog(
        user_id=test_user.id,
        status="planned",
        selected_entity_name="Test Task",
        training_day_id=td.id,
        subtasks=subtasks,
    )
    db_session.add(log)
    await db_session.flush()

    assert log.training_day_id == td.id
    assert len(log.subtasks) == 3
    assert log.subtasks[0]["is_done"]


# --- Subtask toggle ---


@pytest.mark.asyncio
async def test_toggle_subtask_toggles(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Toggling a subtask flips is_done."""
    today = date.today()
    td = TrainingDay(
        user_id=test_user.id,
        target_date=today,
        status="active",
    )
    db_session.add(td)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        status="planned",
        selected_entity_name="Toggle Test",
        training_day_id=td.id,
        subtasks=[{"id": 1, "desc": "Step 1", "is_done": False}],
    )
    db_session.add(log)
    await db_session.flush()

    response = await auth_client.post(
        f"/training/tasks/{log.id}/subtasks/0/toggle",
        follow_redirects=False,
    )
    assert response.status_code == 303

    await db_session.refresh(log)
    assert log.subtasks[0]["is_done"]


# --- Gamification: training mode ---


@pytest.mark.asyncio
async def test_training_completion_skips_streak(db_session: AsyncSession, test_user):
    """Training task completion awards XP but skips streak/achievements."""
    from app.models.entity import Entity

    progress = await get_or_create_progress(db_session, test_user.id)
    assert progress.current_streak == 0

    entity = Entity(
        type="one_time",
        real_name="Training Entity",
        category="Test",
        owner_id=test_user.id,
    )
    db_session.add(entity)
    await db_session.flush()

    today = date.today()
    td = TrainingDay(
        user_id=test_user.id,
        target_date=today,
        status="active",
    )
    db_session.add(td)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="planned",
        selected_entity_name="Training Entity",
        selected_params={"intensity": 1},
        training_day_id=td.id,
    )
    db_session.add(log)
    await db_session.flush()

    result = await on_task_completed(db_session, test_user.id, log)
    assert result["xp_earned"] > 0  # XP still awarded
    assert result["streak"] == 0  # Streak NOT incremented
    assert result["combo"] == 0  # Combo NOT incremented
    assert result["new_achievements"] == 0  # No achievements


# --- Audit fixes: plan generation hardening ---


@pytest.mark.asyncio
async def test_generate_plan_rejects_foreign_private_entity(
    auth_client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch
):
    """Audit: plan must not accept another user's private entity (or any unknown id)."""
    from app.auth import hash_password
    from app.models.user import User

    other = User(email="other@x.com", password_hash=hash_password("secret123"), locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    foreign = Entity(
        type="one_time",
        real_name="Foreign private",
        category="test",
        owner_id=other.id,
        is_public=False,
    )
    db_session.add(foreign)
    await db_session.flush()

    await _make_active_config(db_session, test_user.id)
    plan = {
        "plan_summary": "hi",
        "tasks": [
            {
                "entity_id": str(foreign.id),
                "entity_name": "Foreign private",
                "params": {},
                "subtasks": ["Step 1"],
            }
        ],
    }
    monkeypatch.setattr("app.llm.client.call_llm", await _fake_llm(plan))

    response = await auth_client.post("/training/plan", follow_redirects=False)
    assert response.status_code == 303
    assert "error=" in response.headers["location"]

    days = (await db_session.execute(select(TrainingDay).where(TrainingDay.user_id == test_user.id))).scalars().all()
    assert days == []  # Nothing persisted


@pytest.mark.asyncio
async def test_generate_plan_rejects_out_of_range_params(
    auth_client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch
):
    """Audit: plan params must fit the entity's params_schema."""
    entity = await _make_allowed_entity(db_session, test_user.id)
    await _make_active_config(db_session, test_user.id)

    plan = {
        "plan_summary": "hi",
        "tasks": [
            {
                "entity_id": str(entity.id),
                "entity_name": "Test Activity",
                "params": {"intensity": 99},  # schema allows max 3
                "subtasks": ["Step 1"],
            }
        ],
    }
    monkeypatch.setattr("app.llm.client.call_llm", await _fake_llm(plan))

    response = await auth_client.post("/training/plan", follow_redirects=False)
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    days = (await db_session.execute(select(TrainingDay).where(TrainingDay.user_id == test_user.id))).scalars().all()
    assert days == []


@pytest.mark.asyncio
async def test_generate_plan_sanitizes_subtasks(
    auth_client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch
):
    """REM §7.1: subtasks are capped (count + length) and coerced to strings."""
    entity = await _make_allowed_entity(db_session, test_user.id)
    await _make_active_config(db_session, test_user.id)

    long_desc = "x" * 900
    plan = {
        "plan_summary": "hi",
        "tasks": [
            {
                "entity_id": str(entity.id),
                "entity_name": "Test Activity",
                "params": {"intensity": 2},
                "subtasks": [
                    long_desc,  # must be truncated to 500
                    "   ",  # whitespace-only → dropped
                    123,  # non-string → coerced to "123"
                    None,  # None → "None" coerced, but kept? no — str(None) not empty
                ]
                + [f"step {i}" for i in range(30)],  # 34 raw → capped at 20
            }
        ],
    }
    monkeypatch.setattr("app.llm.client.call_llm", await _fake_llm(plan))

    response = await auth_client.post("/training/plan", follow_redirects=False)
    assert response.status_code == 303

    day = (await db_session.execute(select(TrainingDay).where(TrainingDay.user_id == test_user.id))).scalars().first()
    assert day is not None
    logs = (await db_session.execute(select(ActivityLog).where(ActivityLog.training_day_id == day.id))).scalars().all()
    assert len(logs) == 1
    subtasks = logs[0].subtasks
    assert len(subtasks) <= 20
    for s in subtasks:
        assert isinstance(s["desc"], str)
        assert len(s["desc"]) <= 500
    assert all(s["is_done"] is False for s in subtasks)
    assert any(s["desc"].startswith("x" * 500) for s in subtasks)  # long one truncated
    assert any(s["desc"] == "123" for s in subtasks)  # int coerced to str


@pytest.mark.asyncio
async def test_generate_plan_opted_in_not_assessed_is_planned(
    auth_client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch
):
    """ADR-106: an opted-in entity is approved by default — risk_level is informational."""
    from app.llm.pipeline import filter_automation_eligible

    low = {"id": "a", "risk_level": "low"}
    na = {"id": "b", "risk_level": "not_assessed"}
    high = {"id": "c", "risk_level": "high"}
    elev = {"id": "d", "risk_level": "elevated"}

    eligible = filter_automation_eligible([low, na, high, elev])
    assert [e["id"] for e in eligible] == ["a", "b", "c", "d"]

    # Pipeline: an opted-in entity with risk_level not_assessed is auto-planned.
    entity = await _make_allowed_entity(db_session, test_user.id)
    entity.risk_level = "not_assessed"
    await db_session.flush()
    await _make_active_config(db_session, test_user.id)

    plan = {
        "plan_summary": "hi",
        "tasks": [
            {
                "entity_id": str(entity.id),
                "entity_name": "Test Activity",
                "params": {"intensity": 2},
                "subtasks": ["Step 1"],
            }
        ],
    }
    monkeypatch.setattr("app.llm.client.call_llm", await _fake_llm(plan))

    response = await auth_client.post("/training/plan", follow_redirects=False)
    assert response.status_code == 303
    days = (await db_session.execute(select(TrainingDay).where(TrainingDay.user_id == test_user.id))).scalars().all()
    assert len(days) == 1
    assert days[0].status == "active"  # opted-in not_assessed entity is auto-planned (ADR-106)


@pytest.mark.asyncio
async def test_generate_plan_no_partial_day_on_llm_error(
    auth_client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch
):
    """Audit: an LLM error must not leave a partially-created plan that blocks retry."""
    await _make_active_config(db_session, test_user.id)

    async def failing_llm(**kwargs):
        raise JsonRepairError("boom")

    monkeypatch.setattr("app.llm.client.call_llm", failing_llm)

    response = await auth_client.post("/training/plan", follow_redirects=False)
    assert response.status_code == 303
    assert "error=" in response.headers["location"]

    # No day was persisted → a retry is not blocked by "Plan already exists"
    days = (await db_session.execute(select(TrainingDay).where(TrainingDay.user_id == test_user.id))).scalars().all()
    assert days == []

    response2 = await auth_client.post("/training/plan", follow_redirects=False)
    assert response2.status_code == 303
    assert "Plan+already+exists" not in response2.headers["location"]


@pytest.mark.asyncio
async def test_generate_plan_removes_leftover_empty_plan(
    auth_client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch
):
    """Audit: a leftover empty plan (failed attempt) is replaced on retry."""
    entity = await _make_allowed_entity(db_session, test_user.id)
    await _make_active_config(db_session, test_user.id)

    # Simulate a partial plan committed by a pre-fix failed attempt
    leftover = TrainingDay(user_id=test_user.id, target_date=date.today(), status="planned")
    db_session.add(leftover)
    await db_session.flush()

    plan = {
        "plan_summary": "plan",
        "tasks": [
            {
                "entity_id": str(entity.id),
                "entity_name": "Test Activity",
                "params": {"intensity": 2},
                "subtasks": ["Step 1", "Step 2"],
            }
        ],
    }
    monkeypatch.setattr("app.llm.client.call_llm", await _fake_llm(plan))

    response = await auth_client.post("/training/plan", follow_redirects=False)
    assert response.status_code == 303

    days = (await db_session.execute(select(TrainingDay).where(TrainingDay.user_id == test_user.id))).scalars().all()
    assert len(days) == 1
    assert days[0].status == "active"
    logs = (
        (await db_session.execute(select(ActivityLog).where(ActivityLog.training_day_id == days[0].id))).scalars().all()
    )
    assert len(logs) == 1
    assert logs[0].entity_id == entity.id
    assert logs[0].subtasks == [
        {"id": 1, "desc": "Step 1", "is_done": False},
        {"id": 2, "desc": "Step 2", "is_done": False},
    ]


# --- Audit fixes: journal stored XSS ---@pytest.mark.asyncio
async def test_analyze_day_no_partial_state_on_second_llm_error(
    auth_client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch
):
    """Audit: a failed second LLM call must not commit partial analysis state."""
    await _make_active_config(db_session, test_user.id)
    td = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    db_session.add(td)
    await db_session.flush()

    async def analyze_llm(**kwargs):
        analyze_llm.calls = getattr(analyze_llm, "calls", 0) + 1
        if analyze_llm.calls == 1:
            return {"content": json.dumps({"analysis": "Good day"}), "usage": _USAGE}
        raise JsonRepairError("second call failed")

    monkeypatch.setattr("app.llm.client.call_llm", analyze_llm)

    response = await auth_client.post("/training/analyze", follow_redirects=False)
    assert response.status_code == 303
    assert "error=" in response.headers["location"]

    await db_session.refresh(td)
    assert td.status == "active"  # unchanged
    assert td.analysis_summary is None
    assert td.next_day_suggestion is None


@pytest.mark.asyncio
async def test_add_log_entry_sanitizes_entry_type(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Audit: entry_type is restricted to the allowlist — no stored XSS vector."""
    td = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    db_session.add(td)
    await db_session.flush()

    response = await auth_client.post(
        "/training/log-entry",
        data={
            "training_day_id": str(td.id),
            "time_label": "09:00",
            "entry_type": "<script>alert(1)</script>",
            "actual_value": "x",
        },
    )
    assert response.status_code == 200
    assert "<script>alert(1)" not in response.text

    entry = (
        (await db_session.execute(select(TrainingLogEntry).where(TrainingLogEntry.training_day_id == td.id)))
        .scalars()
        .first()
    )
    assert entry is not None
    assert entry.entry_type == "general_note"  # coerced to safe default


@pytest.mark.asyncio
async def test_add_log_entry_keeps_valid_type(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Valid entry types pass through unchanged."""
    td = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    db_session.add(td)
    await db_session.flush()

    response = await auth_client.post(
        "/training/log-entry",
        data={
            "training_day_id": str(td.id),
            "time_label": "21:00",
            "entry_type": "pressure_check",
        },
    )
    assert response.status_code == 200
    entry = (
        (await db_session.execute(select(TrainingLogEntry).where(TrainingLogEntry.training_day_id == td.id)))
        .scalars()
        .first()
    )
    assert entry.entry_type == "pressure_check"


# --- Manual task creation in a training day (ADR-106) ---


@pytest.mark.asyncio
async def test_manual_training_task_creates_log(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """POST /training/tasks adds a task to today's training day without LLM."""
    entity = await _make_allowed_entity(db_session, test_user.id)
    td = TrainingDay(user_id=test_user.id, target_date=date.today(), status="active")
    db_session.add(td)
    await db_session.flush()

    response = await auth_client.post(
        "/training/tasks",
        data={
            "entity_id": str(entity.id),
            "training_day_id": str(td.id),
            "param_intensity": "2",
            "planned_comment": "manual",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    logs = (
        (await db_session.execute(select(ActivityLog).where(ActivityLog.training_day_id == td.id))).scalars().all()
    )
    assert len(logs) == 1
    assert logs[0].entity_id == entity.id
    assert logs[0].selected_params == {"intensity": 2}
    assert logs[0].status == "planned"
    assert logs[0].planned_comment == "manual"


@pytest.mark.asyncio
async def test_manual_training_task_creates_day_if_missing(
    auth_client: AsyncClient, db_session: AsyncSession, test_user
):
    """POST /training/tasks without training_day_id creates today's day on the fly."""
    entity = await _make_allowed_entity(db_session, test_user.id)

    response = await auth_client.post(
        "/training/tasks",
        data={"entity_id": str(entity.id), "param_intensity": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    days = (await db_session.execute(select(TrainingDay).where(TrainingDay.user_id == test_user.id))).scalars().all()
    assert len(days) == 1
    assert days[0].target_date == date.today()
    logs = (
        (await db_session.execute(select(ActivityLog).where(ActivityLog.training_day_id == days[0].id))).scalars().all()
    )
    assert len(logs) == 1
    assert logs[0].entity_id == entity.id


@pytest.mark.asyncio
async def test_manual_training_task_rejects_foreign_entity(
    auth_client: AsyncClient, db_session: AsyncSession, test_user
):
    """Manual training task must not accept another user's private entity."""
    from app.auth import hash_password
    from app.models.user import User

    other = User(email="other2@x.com", password_hash=hash_password("secret123"), locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    foreign = Entity(
        type="one_time",
        real_name="Foreign private",
        category="test",
        owner_id=other.id,
        is_public=False,
    )
    db_session.add(foreign)
    await db_session.flush()

    response = await auth_client.post(
        "/training/tasks",
        data={"entity_id": str(foreign.id)},
        follow_redirects=False,
    )
    assert response.status_code == 404


# --- Personal entities are eligible without opt-in (ADR-106) ---


@pytest.mark.asyncio
async def test_personal_entity_eligible_without_optin(db_session: AsyncSession, test_user):
    """A personal entity (owner_id == user) appears in the LLM context without opt-in."""
    from app.llm.context_builder import _get_allowed_entities

    entity = Entity(
        type="one_time",
        real_name="My Personal",
        category="test",
        owner_id=test_user.id,
        is_public=False,
        params_schema={"intensity": {"type": "integer", "min": 1, "max": 3}},
    )
    db_session.add(entity)
    await db_session.flush()
    # No opt-in row — ADR-106: personal is approved by default.

    allowed = await _get_allowed_entities(db_session, test_user.id)
    assert any(e["name"] == "My Personal" for e in allowed)


@pytest.mark.asyncio
async def test_personal_entity_optout_respected(db_session: AsyncSession, test_user):
    """An explicit opt-out still excludes a personal entity from the LLM context."""
    from app.llm.context_builder import _get_allowed_entities

    entity = Entity(
        type="one_time",
        real_name="My Opted-Out",
        category="test",
        owner_id=test_user.id,
        is_public=False,
    )
    db_session.add(entity)
    await db_session.flush()
    db_session.add(UserEntityOptIn(user_id=test_user.id, entity_id=entity.id, is_opted_in=False))
    await db_session.flush()

    allowed = await _get_allowed_entities(db_session, test_user.id)
    assert not any(e["name"] == "My Opted-Out" for e in allowed)


@pytest.mark.asyncio
async def test_create_entity_auto_optin(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Creating a personal entity auto-creates an opt-in row (ADR-106)."""
    response = await auth_client.post(
        "/entities/",
        data={
            "real_name": "Auto Optin Task",
            "type": "one_time",
            "category": "Test",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entity = (
        (await db_session.execute(select(Entity).where(Entity.real_name == "Auto Optin Task"))).scalar_one_or_none()
    )
    assert entity is not None
    opt_in = (
        await db_session.execute(
            select(UserEntityOptIn).where(
                UserEntityOptIn.user_id == test_user.id,
                UserEntityOptIn.entity_id == entity.id,
            )
        )
    ).scalar_one_or_none()
    assert opt_in is not None
    assert opt_in.is_opted_in


def test_render_log_entry_row_escapes_user_fields():
    """Audit: the HTMX row renderer escapes all user-controlled fields."""
    from app.api.training import _render_log_entry_row

    entry = TrainingLogEntry(
        id=uuid.uuid4(),
        entry_type="<b>bold</b>",
        time_label="<script>alert(1)</script>",
        unit='"><img src=x onerror=alert(1)>',
        planned_value="<p>planned</p>",
        actual_value='" onfocus=alert(1) ',
        notes="<textarea>",
        is_extra=True,
    )
    html = _render_log_entry_row(entry)
    # No raw tags / event handlers may survive — everything is HTML-escaped
    assert "<script>alert(1)" not in html
    assert "<b>bold</b>" not in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html
    assert "&lt;p&gt;planned&lt;/p&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
