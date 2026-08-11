"""Phase 3 UI tests (update.md Q11): catalog category filters, manual task creation,
completion card with actual parameters.

Covers ADR-035 (category tree filters), ADR-041 (dynamic params form),
ADR-040 (transition with actual_parameters / completion_comment).
"""

import pytest
from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.category import ActivityCategory
from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn

# ── Catalog: hierarchical category filters ──────────────────────────────


@pytest.mark.asyncio
async def test_catalog_filter_by_category_id(db_session, auth_client, test_user):
    """Entities are filtered by normalized category_id (ADR-035)."""
    cat = ActivityCategory(slug="impact", title="Impact Play")
    sub = ActivityCategory(slug="spanking", title="Spanking", parent=cat)
    db_session.add_all([cat, sub])
    await db_session.flush()

    e1 = Entity(type="one_time", real_name="A", category="Impact Play", category_id=cat.id, owner_id=test_user.id)
    e2 = Entity(type="one_time", real_name="B", category="Spanking", category_id=sub.id, owner_id=test_user.id)
    e3 = Entity(type="one_time", real_name="C", category="Other", owner_id=test_user.id)
    db_session.add_all([e1, e2, e3])
    await db_session.flush()

    # Filter by root category → includes descendants
    r = await auth_client.get(f"/entities/catalog?category_id={cat.id}")
    assert r.status_code == 200
    assert ">A<" in r.text or "A</h3>" in r.text
    assert ">B<" in r.text or "B</h3>" in r.text
    assert "C</h3>" not in r.text

    # Filter by child category → only its own entities
    r2 = await auth_client.get(f"/entities/catalog?category_id={sub.id}")
    assert r2.status_code == 200
    assert "A</h3>" not in r2.text
    assert "B</h3>" in r2.text


@pytest.mark.asyncio
async def test_catalog_category_chips_from_tree(db_session, auth_client, test_user):
    """Root categories appear as filter chips; category title from reference table."""
    cat = ActivityCategory(slug="impact", title="Impact Play")
    db_session.add(cat)
    await db_session.flush()
    e = Entity(
        type="one_time",
        real_name="Spank",
        category="Impact Play",
        category_id=cat.id,
        owner_id=test_user.id,
    )
    db_session.add(e)
    await db_session.flush()

    r = await auth_client.get("/entities/catalog")
    assert r.status_code == 200
    # chip link for the root category
    assert f"category_id={cat.id}" in r.text
    # entity card shows the reference title
    assert "Impact Play" in r.text


@pytest.mark.asyncio
async def test_catalog_legacy_category_filter_still_works(db_session, auth_client, test_user):
    """Legacy ?category= string filter remains for non-normalized entities."""
    e = Entity(type="one_time", real_name="Legacy", category="old_string_cat", owner_id=test_user.id)
    db_session.add(e)
    await db_session.flush()

    r = await auth_client.get("/entities/catalog?category=old_string_cat")
    assert r.status_code == 200
    assert "Legacy</h3>" in r.text


# ── Manual task creation: params form ───────────────────────────────────


@pytest.mark.asyncio
async def test_params_form_renders_dsl_fields(db_session, auth_client, test_user):
    """GET /tasks/params-form renders inputs for each DSL param type."""
    schema = [
        {"key": "count", "title": "Count", "type": "integer", "min": 1, "max": 100},
        {"key": "intensity", "title": "Intensity", "type": "enum", "options": ["1", "2", "3"]},
        {"key": "notes", "title": "Notes", "type": "text"},
        {"key": "loud", "title": "Loud", "type": "boolean"},
    ]
    entity = Entity(type="one_time", real_name="Test", category="test", owner_id=test_user.id, params_schema=schema)
    db_session.add(entity)
    await db_session.flush()

    r = await auth_client.get(f"/tasks/params-form?entity_id={entity.id}")
    assert r.status_code == 200
    assert 'name="param_count"' in r.text
    assert 'name="param_intensity"' in r.text
    assert 'name="param_notes"' in r.text
    assert 'name="param_loud"' in r.text


@pytest.mark.asyncio
async def test_params_form_prefix_for_actual(db_session, auth_client, test_user):
    """prefix=actual_ renames fields (used by the completion card)."""
    schema = [{"key": "count", "title": "Count", "type": "integer"}]
    entity = Entity(type="one_time", real_name="Test", category="test", owner_id=test_user.id, params_schema=schema)
    db_session.add(entity)
    await db_session.flush()

    r = await auth_client.get(f"/tasks/params-form?entity_id={entity.id}&prefix=actual_")
    assert r.status_code == 200
    assert 'name="actual_count"' in r.text
    assert 'name="param_count"' not in r.text


@pytest.mark.asyncio
async def test_params_form_cross_user_404(db_session, auth_client, test_user):
    from app.models.user import User

    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    entity = Entity(type="one_time", real_name="Private", category="test", owner_id=other.id, is_public=False)
    db_session.add(entity)
    await db_session.flush()

    r = await auth_client.get(f"/tasks/params-form?entity_id={entity.id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_manual_task_creates_planned(db_session, auth_client, test_user):
    """POST /tasks/create builds a planned ActivityLog from typed params."""
    schema = [
        {"key": "count", "title": "Count", "type": "integer", "required": True, "min": 1},
        {"key": "intensity", "title": "Intensity", "type": "enum", "options": ["1", "2", "3", "4", "5"]},
    ]
    entity = Entity(
        type="one_time",
        real_name="Spanking",
        category="test",
        owner_id=test_user.id,
        params_schema=schema,
        task_template={"template": "{count} strikes, intensity {intensity}/5"},
    )
    db_session.add(entity)
    await db_session.flush()

    r = await auth_client.post(
        "/tasks/create",
        data={
            "entity_id": str(entity.id),
            "param_count": "10",
            "param_intensity": "3",
            "planned_comment": "evening session",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    result = await db_session.execute(select(ActivityLog).where(ActivityLog.user_id == test_user.id))
    log = result.scalar_one()
    assert log.status == "planned"
    assert log.selected_params == {"count": 10, "intensity": "3"}
    assert log.planned_comment == "evening session"
    assert log.title_override == "10 strikes, intensity 3/5"


@pytest.mark.asyncio
async def test_create_manual_task_invalid_params_rejected(db_session, auth_client, test_user):
    """Invalid params (below min) → redirect with error, no task created."""
    schema = [{"key": "count", "title": "Count", "type": "integer", "required": True, "min": 5}]
    entity = Entity(type="one_time", real_name="Spanking", category="test", owner_id=test_user.id, params_schema=schema)
    db_session.add(entity)
    await db_session.flush()

    r = await auth_client.post(
        "/tasks/create",
        data={"entity_id": str(entity.id), "param_count": "2"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error=" in r.headers["location"]

    result = await db_session.execute(select(ActivityLog).where(ActivityLog.user_id == test_user.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_create_manual_task_cross_user_404(db_session, auth_client, test_user):
    from app.models.user import User

    other = User(email="other@example.com", password_hash="x", locale="en", theme="dark")
    db_session.add(other)
    await db_session.flush()
    entity = Entity(type="one_time", real_name="Private", category="test", owner_id=other.id, is_public=False)
    db_session.add(entity)
    await db_session.flush()

    r = await auth_client.post("/tasks/create", data={"entity_id": str(entity.id)})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_tasks_page_lists_create_entities(db_session, auth_client, test_user):
    """Only opted-in entities appear in the manual creation select."""
    ent = Entity(type="one_time", real_name="Opted", category="test", owner_id=test_user.id, is_public=True)
    ent2 = Entity(type="one_time", real_name="NotOpted", category="test", owner_id=test_user.id)
    db_session.add_all([ent, ent2])
    await db_session.flush()
    db_session.add(UserEntityOptIn(user_id=test_user.id, entity_id=ent.id, is_opted_in=True))
    await db_session.flush()

    r = await auth_client.get("/tasks/")
    assert r.status_code == 200
    assert 'value="' + str(ent.id) + '">Opted' in r.text
    assert "NotOpted" not in r.text


# ── Completion card: transition with actual parameters ──────────────────


@pytest.mark.asyncio
async def test_transition_completed_saves_actual_params_and_comment(db_session, auth_client, test_user):
    """Transition to completed stores actual_parameters + completion_comment (ADR-041)."""
    entity = Entity(type="one_time", real_name="Spanking", category="test", owner_id=test_user.id)
    db_session.add(entity)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="planned",
        selected_entity_name="Spanking",
    )
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(
        f"/api/v2/tasks/{log.id}/transition",
        json={
            "to_status": "completed",
            "comment": "went great",
            "actual_parameters": {"count": 15, "intensity": 4},
        },
    )
    assert r.status_code == 200
    await db_session.refresh(log)
    assert log.status == "completed"
    assert log.actual_parameters == {"count": 15, "intensity": 4}
    assert log.completion_comment == "went great"
    assert log.completed_at is not None


@pytest.mark.asyncio
async def test_transition_partial_saves_actual_params(db_session, auth_client, test_user):
    log = ActivityLog(user_id=test_user.id, status="in_progress", selected_entity_name="T")
    db_session.add(log)
    await db_session.flush()

    r = await auth_client.post(
        f"/api/v2/tasks/{log.id}/transition",
        json={"to_status": "partially_completed", "actual_parameters": {"count": 5}},
    )
    assert r.status_code == 200
    await db_session.refresh(log)
    assert log.status == "partially_completed"
    assert log.actual_parameters == {"count": 5}
    assert log.completed_at is not None


@pytest.mark.asyncio
async def test_tasks_page_shows_quick_actions_and_stats(db_session, auth_client, test_user):
    """The tasks page renders status stats and quick-action buttons."""
    for status in ("planned", "completed"):
        db_session.add(ActivityLog(user_id=test_user.id, status=status, selected_entity_name="T"))
    await db_session.flush()

    r = await auth_client.get("/tasks/")
    assert r.status_code == 200
    # stats chips
    assert "Status summary" in r.text
    # quick action buttons present for a planned task
    assert "data-transition=" in r.text
    # status labels localized
    assert "planned" in r.text
