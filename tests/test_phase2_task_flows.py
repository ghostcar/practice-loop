"""Phase 2 (Session 58) tests — typed parameter DSL, title generator, status transitions.

Covers ADR-041 (typed params), ADR-042 (title generation), ADR-040
(transition API + audit).
"""

import pytest
from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.task_history import ActivityTaskHistory
from app.models.task_status import COMPLETED, PLANNED
from app.params import COMMON_PARAMETERS, normalize_schema, validate_params
from app.title_gen import generate_title

# ── ADR-041: typed parameter DSL ────────────────────────────────────────


def test_normalize_legacy_compact_schema():
    """Legacy compact map normalizes into definitions with defaults."""
    defs = normalize_schema({"duration_minutes": {"min": 10, "max": 20}, "participants": 1})
    keys = {d["key"] for d in defs}
    assert keys == {"duration_minutes", "participants"}
    lit = next(d for d in defs if d["key"] == "participants")
    assert lit["type"] == "literal"
    assert lit["value"] == 1
    assert lit["required"] is True


def test_normalize_structured_schema():
    """Structured definition list (ADR-041) with type/options/visible_when."""
    schema = [
        {"key": "count", "title": "Count", "type": "integer", "required": True, "min": 1, "max": 100},
        {"key": "intensity", "type": "enum", "options": ["1", "2", "3", "4", "5"], "allow_custom_value": False},
        {"key": "position", "type": "string", "visible_when": {"count": {"min": 1}}},
        {"key": "modifiers", "type": "multi_enum", "options": ["counting"], "required": False},
    ]
    defs = normalize_schema(schema)
    assert len(defs) == 4
    assert defs[0]["type"] == "integer"
    assert defs[0]["required"] is True
    assert defs[1]["options"] == ["1", "2", "3", "4", "5"]
    assert defs[2]["visible_when"] == {"count": {"min": 1}}


def test_normalize_rejects_bad_schema():
    with pytest.raises(ValueError):
        normalize_schema([{"type": "integer"}])  # missing key
    with pytest.raises(ValueError):
        normalize_schema([{"key": "x", "type": "evil"}])  # unknown type
    with pytest.raises(ValueError):
        normalize_schema([{"key": "x", "type": "enum"}])  # enum without options
    with pytest.raises(ValueError):
        normalize_schema("not-a-schema")  # wrong shape


def test_validate_params_no_eval():
    """Validation is declarative — no code execution, bounds/enum respected."""
    schema = [
        {"key": "count", "type": "integer", "required": True, "min": 1, "max": 100},
        {"key": "intensity", "type": "enum", "options": ["1", "2", "3", "4", "5"]},
    ]
    assert validate_params(schema, {"count": 10, "intensity": "3"}) == []
    assert validate_params(schema, {"count": 0})  # below min
    assert validate_params(schema, {"intensity": "9"})  # not in enum
    assert validate_params(schema, {"count": "ten"})  # type mismatch
    assert validate_params(schema, {"intensity": "3"})  # missing required count
    assert validate_params(schema, None)  # missing dict with required


def test_common_parameters_reusable():
    """Common parameter set from update.md is available and valid."""
    assert "tool" in COMMON_PARAMETERS
    assert "intensity" in COMMON_PARAMETERS
    assert COMMON_PARAMETERS["intensity"]["type"] == "enum"
    # Every common param normalizes cleanly
    for key, d in COMMON_PARAMETERS.items():
        defs = normalize_schema([{"key": key, **d}])
        assert defs[0]["key"] == key


def test_legacy_validator_still_passes():
    """Old-style schema (used by LLM validator) still validates via DSL."""
    from app.llm.validator import validate_params_against_schema

    schema = {"duration_minutes": {"type": "number", "min": 5, "max": 240}, "notes": {"optional": True}}
    assert validate_params_against_schema({"duration_minutes": 30}, schema) == []
    assert validate_params_against_schema({"duration_minutes": 999}, schema)  # above max


# ── ADR-042: title generator ────────────────────────────────────────────


def test_title_override_wins():
    assert generate_title("Spanking", {"count": 10}, title_override="Custom") == "Custom"


def test_title_template_renders_and_skips_empty():
    """Template parts are skipped when empty (ADR-042 examples)."""
    tpl = "{count} {unit} — {activity_title}, {tool}, zone: {target_area}, intensity {intensity}/5"
    title = generate_title(
        "Spanking",
        {"count": 10, "unit": "strikes", "tool": "hand", "target_area": "buttocks", "intensity": 3},
        template=tpl,
    )
    assert "10 strikes" in title
    assert "Spanking" in title
    assert "hand" in title
    assert "intensity 3/5" in title

    # Missing optional params are simply skipped — no ", ," artifacts
    title2 = generate_title("Chastity cage", {"duration": "4 hours"}, template="{activity_title}, duration: {duration}")
    assert title2 == "Chastity cage, duration: 4 hours"


def test_title_fallback_chain():
    """No template → param list → plain activity title → free task."""
    assert generate_title("Massage", {"duration_minutes": 20}) == "Massage: duration minutes: 20"
    assert generate_title("Massage", None) == "Massage"
    assert generate_title("", None) == "Free task: [manual title]"
    assert generate_title("Massage", None, manual_title="Manual") == "Manual"


def test_title_localized_ru():
    """RU locale uses localized labels (ADR-042 i18n)."""
    title = generate_title(
        "Порка",
        {"count": 10, "intensity": 3, "target_area": "ягодицы"},
        locale="ru",
    )
    assert "интенсивность: 3/5" in title
    assert "зона: ягодицы" in title

    title2 = generate_title("", None, locale="ru")
    assert title2 == "Свободная задача: [ручной заголовок]"


def test_title_enum_option_titles():
    """Enum option display titles are resolved from schema."""
    schema = [{"key": "intensity", "type": "enum", "options": [{"value": "3", "title": "Medium"}]}]
    title = generate_title("Task", {"intensity": "3"}, schema=schema)
    assert "intensity: Medium" in title


# ── ADR-040: transition API + audit ─────────────────────────────────────


@pytest.mark.asyncio
async def test_transition_skips_cancels_with_audit(db_session, auth_client, test_user):
    """planned → skipped / cancelled via API, no reward, audit recorded."""
    log = ActivityLog(user_id=test_user.id, status="planned", selected_entity_name="T")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(
        f"/api/v2/tasks/{log.id}/transition",
        json={"to_status": "skipped", "comment": "no time today"},
    )
    assert r.status_code == 200
    await db_session.refresh(log)
    assert log.status == "skipped"

    # audit row
    result = await db_session.execute(select(ActivityTaskHistory).where(ActivityTaskHistory.task_id == log.id))
    h = result.scalar_one()
    assert h.previous_status == "planned"
    assert h.new_status == "skipped"
    assert h.comment == "no time today"
    assert h.actor_id == test_user.id


@pytest.mark.asyncio
async def test_transition_cancel_from_planned(db_session, auth_client, test_user):
    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(f"/api/v2/tasks/{log.id}/transition", json={"to_status": "cancelled"})
    assert r.status_code == 200
    await db_session.refresh(log)
    assert log.status == "cancelled"


@pytest.mark.asyncio
async def test_transition_illegal_rejected(db_session, auth_client, test_user):
    """completed → stopped is illegal; draft → completed is illegal."""
    log = ActivityLog(user_id=test_user.id, status="completed")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(f"/api/v2/tasks/{log.id}/transition", json={"to_status": "stopped"})
    assert r.status_code == 409  # conflict — illegal transition

    r2 = await auth_client.post(f"/api/v2/tasks/{log.id}/transition", json={"to_status": "draft"})
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_transition_completed_grants_reward(db_session, auth_client, test_user):
    """planned → completed through the flow API grants XP (on_task_completed)."""

    entity = Entity(type="one_time", real_name="T", category="test", owner_id=test_user.id)
    db_session.add(entity)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="planned",
        selected_entity_name="T",
        selected_params={"intensity": 1},
    )
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(f"/api/v2/tasks/{log.id}/transition", json={"to_status": "completed"})
    assert r.status_code == 200
    body = r.json()
    assert body["xp_earned"] > 0

    await db_session.refresh(log)
    assert log.status == "completed"
    assert log.completed_at is not None


@pytest.mark.asyncio
async def test_transition_stopped_applies_penalty(db_session, auth_client, test_user):
    """planned → stopped applies XP penalty (ADR-029) and records audit."""

    entity = Entity(type="one_time", real_name="T", category="test", owner_id=test_user.id)
    db_session.add(entity)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="planned",
        selected_entity_name="T",
    )
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(f"/api/v2/tasks/{log.id}/transition", json={"to_status": "stopped"})
    assert r.status_code == 200
    body = r.json()
    assert body["xp_penalty"] > 0

    await db_session.refresh(log)
    assert log.status == "stopped"
    assert log.penalty_applied is True


@pytest.mark.asyncio
async def test_transition_unknown_status_rejected(db_session, auth_client, test_user):
    log = ActivityLog(user_id=test_user.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(f"/api/v2/tasks/{log.id}/transition", json={"to_status": "bogus"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_transition_graph_endpoint(db_session, auth_client, test_user):
    r = await auth_client.get("/api/v2/tasks/transitions")
    assert r.status_code == 200
    data = r.json()
    assert "statuses" in data and len(data["statuses"]) == 11
    assert COMPLETED in data["transitions"][PLANNED]


@pytest.mark.asyncio
async def test_transition_cross_user_404(db_session, auth_client, test_user):
    """Another user's task is not visible (404)."""
    from app.models.user import User

    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    log = ActivityLog(user_id=other.id, status="planned")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(f"/api/v2/tasks/{log.id}/transition", json={"to_status": "cancelled"})
    assert r.status_code == 404
