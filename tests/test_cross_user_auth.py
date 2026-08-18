"""Cross-user authorization tests: user A cannot access/modify user B's resources.

REMEDIATION_SPEC §9.2: «каждый запрос к пользовательскому объекту фильтруется по user_id или проверенной роли;
тесты обязаны проверять cross-user read/write для каждого семейства endpoints»
"""

from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.activity_log import ActivityLog
from app.models.calendar import AvailabilityWindow, CalendarTemplate
from app.models.entity import Entity
from app.models.life import InventoryItem, ScheduleRule
from app.models.llm_config import LLMProviderConfig
from app.models.points import PenaltyRedemption, PointsProfile
from app.models.session import ActivitySession
from app.models.training import TrainingDay
from app.models.user import User

# ── Helpers ──────────────────────────────────────────────────────────


def _make_auth_headers(user: User) -> dict:
    """Build auth headers for a specific user."""
    import secrets

    from app.auth import create_access_token

    token = create_access_token(user.id)
    csrf = secrets.token_hex(32)
    return {"Cookie": f"access_token={token}; csrf_token={csrf}", "X-CSRF-Token": csrf}


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
async def user_b(db_session: AsyncSession) -> User:
    """Second user for cross-user tests."""
    from app.auth import hash_password

    user = User(email="other@example.com", password_hash=hash_password("secret123"), locale="en", theme="dark")
    db_session.add(user)
    await db_session.flush()
    return user


# ═══════════════════════════════════════════════════════════════════════
# Entity gamification config
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_read_private_entity_gamification(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot read gamification config of user B's private entity."""
    entity = Entity(type="one_time", real_name="B's private", category="test", owner_id=user_b.id, is_public=False)
    db_session.add(entity)
    await db_session.flush()

    response = await auth_client.get(f"/api/v2/entities/{entity.id}/gamification")
    assert response.status_code == 404  # Not found (should not reveal existence)


@pytest.mark.asyncio
async def test_cannot_update_others_gamification(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot update gamification config of user B's entity."""
    entity = Entity(type="one_time", real_name="B's entity", category="test", owner_id=user_b.id, is_public=True)
    db_session.add(entity)
    await db_session.flush()

    payload = {
        "points": {"base": 100},
        "penalties": {"enabled": False},
        "bonuses": [],
        "thresholds": {"negative": -50, "warning": 0, "good": 50},
    }
    response = await auth_client.put(f"/api/v2/entities/{entity.id}/gamification", json=payload)
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Entity opt-in
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_opt_into_private_entity(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot opt into user B's private entity."""
    entity = Entity(type="one_time", real_name="B's private", category="test", owner_id=user_b.id, is_public=False)
    db_session.add(entity)
    await db_session.flush()

    response = await auth_client.post(
        f"/entities/{entity.id}/opt-in",
        data={"is_opted_in": True, "desire_level": "want"},
        follow_redirects=False,
    )
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Calendar
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_delete_others_calendar_window(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot delete a window from user B's calendar template."""
    tpl = CalendarTemplate(user_id=user_b.id, name="B's template")
    db_session.add(tpl)
    await db_session.flush()

    window = AvailabilityWindow(
        template_id=tpl.id, day_of_week=0, start_time=time(9, 0), end_time=time(17, 0), label="work", policy="allowed"
    )
    db_session.add(window)
    await db_session.flush()

    response = await auth_client.delete(f"/calendar/templates/{tpl.id}/windows/{window.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_others_template(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot delete user B's calendar template."""
    tpl = CalendarTemplate(user_id=user_b.id, name="B's template")
    db_session.add(tpl)
    await db_session.flush()

    response = await auth_client.delete(f"/calendar/templates/{tpl.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_create_override_on_others_template(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot create an override using user B's template."""
    tpl = CalendarTemplate(user_id=user_b.id, name="B's template")
    db_session.add(tpl)
    await db_session.flush()

    response = await auth_client.post(
        "/calendar/overrides",
        json={"template_id": str(tpl.id), "start_date": "2026-08-10", "end_date": "2026-08-20", "label": "Vacation"},
    )
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Schedule rules
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_delete_others_schedule_rule(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot delete user B's schedule rule."""
    rule = ScheduleRule(
        user_id=user_b.id, day_of_week=0, start_time=time(6, 0), end_time=time(7, 0), task_type="mandatory"
    )
    db_session.add(rule)
    await db_session.flush()

    response = await auth_client.delete(f"/api/v2/schedule/rules/{rule.id}")
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Inventory
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_update_others_inventory(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot update user B's inventory item."""
    item = InventoryItem(user_id=user_b.id, category="test", name="B's item", quantity=1, quantity_needed=1)
    db_session.add(item)
    await db_session.flush()

    response = await auth_client.put(
        f"/api/v2/inventory/{item.id}",
        json={"name": "Hacked"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_others_inventory(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot delete user B's inventory item."""
    item = InventoryItem(user_id=user_b.id, category="test", name="B's item", quantity=1, quantity_needed=1)
    db_session.add(item)
    await db_session.flush()

    response = await auth_client.delete(f"/api/v2/inventory/{item.id}")
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Points profiles
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_delete_others_points_profile(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot delete user B's points profile."""
    profile = PointsProfile(user_id=user_b.id, name="B's profile", config={"points": {"base": 10}})
    db_session.add(profile)
    await db_session.flush()

    response = await auth_client.delete(f"/api/v2/points/profiles/{profile.id}")
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Penalty redemptions
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_complete_others_redemption(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot complete user B's penalty redemption."""
    redemption = PenaltyRedemption(
        user_id=user_b.id, redemption_type="clothespins", duration_min=10, escalation_level=1, points_value=5
    )
    db_session.add(redemption)
    await db_session.flush()

    response = await auth_client.post(f"/api/v2/points/redemptions/{redemption.id}/complete")
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Sessions
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_start_others_session(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot start user B's session."""
    session = ActivitySession(owner_id=user_b.id, status="created")
    db_session.add(session)
    await db_session.flush()

    response = await auth_client.post(f"/sessions/{session.id}/start", follow_redirects=False)
    assert response.status_code == 404

    await db_session.refresh(session)
    assert session.status == "created"  # Should remain 'created' — not started


@pytest.mark.asyncio
async def test_cannot_end_others_session(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot end user B's session."""
    session = ActivitySession(owner_id=user_b.id, status="active")
    db_session.add(session)
    await db_session.flush()

    response = await auth_client.post(f"/sessions/{session.id}/end", follow_redirects=False)
    assert response.status_code == 404

    await db_session.refresh(session)
    assert session.status == "active"  # Should remain 'active'


# ═══════════════════════════════════════════════════════════════════════
# Notifications
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_mark_others_notification(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot mark user B's notification as read."""
    from app.models.notification import Notification

    notif = Notification(user_id=user_b.id, type="level_up", title="Congrats", body="Level up!")
    db_session.add(notif)
    await db_session.flush()

    response = await auth_client.post(f"/notifications/{notif.id}/read", follow_redirects=False)
    assert response.status_code == 303

    await db_session.refresh(notif)
    assert not notif.is_read  # Should remain unread


# ═══════════════════════════════════════════════════════════════════════
# LLM configs
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_delete_others_llm_config(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot delete user B's LLM config."""
    config = LLMProviderConfig(
        user_id=user_b.id, provider_name="OpenAI", api_base_url="https://api.openai.com", model_name="gpt-4"
    )
    db_session.add(config)
    await db_session.flush()

    response = await auth_client.post(f"/llm-configs/{config.id}/delete", follow_redirects=False)
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Training
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_complete_others_training_task(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot complete user B's training task."""
    td = TrainingDay(user_id=user_b.id, target_date=date.today(), status="active")
    db_session.add(td)
    await db_session.flush()

    log = ActivityLog(
        user_id=user_b.id,
        status="planned",
        selected_entity_name="B's task",
        training_day_id=td.id,
    )
    db_session.add(log)
    await db_session.flush()

    response = await auth_client.post(f"/training/tasks/{log.id}/complete", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_toggle_others_subtask(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot toggle user B's subtask."""
    td = TrainingDay(user_id=user_b.id, target_date=date.today(), status="active")
    db_session.add(td)
    await db_session.flush()

    log = ActivityLog(
        user_id=user_b.id,
        status="planned",
        selected_entity_name="B's task",
        training_day_id=td.id,
        subtasks=[{"id": 1, "desc": "Step 1", "is_done": False}],
    )
    db_session.add(log)
    await db_session.flush()

    response = await auth_client.post(f"/training/tasks/{log.id}/subtasks/0/toggle", follow_redirects=False)
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Activity logs (tasks)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cannot_complete_others_task(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot complete user B's activity log."""
    log = ActivityLog(user_id=user_b.id, status="planned", selected_entity_name="B's task")
    db_session.add(log)
    await db_session.flush()

    response = await auth_client.post(f"/tasks/{log.id}/complete", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_interrupt_others_task(auth_client: AsyncClient, db_session: AsyncSession, user_b):
    """User A cannot interrupt user B's activity log."""
    log = ActivityLog(user_id=user_b.id, status="planned", selected_entity_name="B's task")
    db_session.add(log)
    await db_session.flush()

    response = await auth_client.post(f"/tasks/{log.id}/interrupt", follow_redirects=False)
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Admin
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_non_admin_cannot_access_admin(auth_client: AsyncClient):
    """Regular user cannot access /admin."""
    response = await auth_client.get("/admin/", follow_redirects=False)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_seed(auth_client: AsyncClient):
    """Regular user cannot seed entities."""
    response = await auth_client.post("/admin/seed-entities", follow_redirects=False)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_seed_with_form_csrf_token_passes(db_session: AsyncSession):
    """Admin POST /admin/seed-entities with form-encoded csrf_token is accepted (S51).

    Regression for the reported bug: native form POSTs without a hidden
    csrf_token field returned 403 'CSRF token missing or invalid'.
    """
    import secrets

    from httpx import ASGITransport, AsyncClient

    from app.auth import create_access_token, hash_password
    from app.models.user import User

    admin = User(
        email="admin@example.com",
        password_hash=hash_password("secret123"),
        locale="en",
        theme="dark",
        role="admin",
    )
    db_session.add(admin)
    await db_session.flush()

    token = create_access_token(admin.id)
    csrf = secrets.token_hex(32)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Cookie": f"access_token={token}; csrf_token={csrf}"},
    ) as client:
        # No X-CSRF-Token header — exactly like a native HTML form submit
        response = await client.post(
            "/admin/seed-entities",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
    assert response.status_code == 303

    # Entities were actually seeded
    result = await db_session.execute(select(Entity))
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_admin_seed_without_csrf_field_rejected(db_session: AsyncSession):
    """Admin POST /admin/seed-entities without csrf_token form field → 403 (S51)."""
    import secrets

    from httpx import ASGITransport, AsyncClient

    from app.auth import create_access_token, hash_password
    from app.models.user import User

    admin = User(
        email="admin2@example.com",
        password_hash=hash_password("secret123"),
        locale="en",
        theme="dark",
        role="admin",
    )
    db_session.add(admin)
    await db_session.flush()

    token = create_access_token(admin.id)
    csrf = secrets.token_hex(32)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Cookie": f"access_token={token}; csrf_token={csrf}"},
    ) as client:
        response = await client.post("/admin/seed-entities", data={}, follow_redirects=False)
    assert response.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# CSRF
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_post_without_csrf_header_rejected(auth_client: AsyncClient, db_session: AsyncSession):
    """POST with auth cookie but no CSRF header is rejected."""
    # Remove CSRF header but keep cookie
    auth_client.headers.pop("X-CSRF-Token", None)

    response = await auth_client.post("/sessions", follow_redirects=False)
    assert response.status_code == 403
