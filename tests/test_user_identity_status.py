import uuid

import pytest

from app.models.user import User
from app.services.identity_registry import (
    DEFAULT_STATUS_TAGS,
    PHYSIOLOGY_TYPES,
    PORTAL_ROLES,
    PRIMARY_ROLES,
)
from app.services.identity_service import (
    add_status_tag,
    ai_assign_identity,
    get_active_tags,
    get_addressing_title,
    get_effective_display_name,
    has_status_tag,
    on_wear_breached,
    on_wear_checkin_success,
    on_wear_status_change,
    remove_status_tag,
    update_user_identity,
    validate_portal_roles,
)


def _make_user(**kwargs) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4().hex[:6]}@example.com",
        display_name=kwargs.get("display_name", "Test User"),
        portal_name=kwargs.get("portal_name"),
        ai_designation=kwargs.get("ai_designation"),
        primary_role=kwargs.get("primary_role", "submissive"),
        portal_roles=kwargs.get("portal_roles", []),
        status_tags=kwargs.get("status_tags", {"permanent": [], "standing": [], "dynamic": []}),
        ai_identity_locked=kwargs.get("ai_identity_locked", False),
        physiology=kwargs.get("physiology", "male"),
        ai_status_reason=kwargs.get("ai_status_reason"),
        password_hash="dummy_hash",
    )
    return u


def test_registry_taxonomy_loaded():
    assert "submissive" in PRIMARY_ROLES
    assert "dominant" in PRIMARY_ROLES
    assert "pet" in PORTAL_ROLES
    assert "chastity_captive" in PORTAL_ROLES
    assert "male" in PHYSIOLOGY_TYPES
    assert "permanent" in DEFAULT_STATUS_TAGS


def test_role_compatibility():
    # Submissive can have slave, pet, brat
    sub_roles = validate_portal_roles("submissive", ["pet", "slave", "invalid_role"])
    assert "pet" in sub_roles
    assert "slave" in sub_roles
    assert "invalid_role" not in sub_roles

    # Dominant cannot have slave or pet
    dom_roles = validate_portal_roles("dominant", ["pet", "slave", "observer"])
    assert dom_roles == ["observer"]


def test_get_effective_display_name():
    u = _make_user(display_name="Alice", portal_name="Puppy", ai_designation="Pet #1")
    # Without discretion
    assert get_effective_display_name(u, discretion_active=False) == "Puppy (Pet #1)"

    # With discretion active -> fallback to neutral display_name
    assert get_effective_display_name(u, discretion_active=True) == "Alice"

    # Without portal name
    u2 = _make_user(display_name="Bob", portal_name=None, ai_designation=None)
    assert get_effective_display_name(u2, discretion_active=False) == "Bob"


def test_get_addressing_title():
    u = _make_user(
        display_name="Alice",
        portal_name="Стелла",
        ai_designation="Sub #07",
        primary_role="submissive",
        portal_roles=["pet"],
    )
    assert "Стелла (Sub #07)" in get_addressing_title(u, form="formal")
    assert get_addressing_title(u, form="directive") == "[Sub #07] Стелла"
    assert get_addressing_title(u, form="affectionate") == "Хороший Стелла"

    # Discretion suppresses role titles
    assert get_addressing_title(u, form="directive", discretion_active=True) == "Alice"


def test_update_user_identity_manual():
    u = _make_user(ai_identity_locked=False)
    update_user_identity(
        u,
        portal_name="NewName",
        ai_designation="Sub #99",
        primary_role="submissive",
        portal_roles=["pet", "brat"],
        physiology="female",
    )
    assert u.portal_name == "NewName"
    assert u.ai_designation == "Sub #99"
    assert u.physiology == "female"
    assert "pet" in u.portal_roles


def test_update_user_identity_locked_rejection():
    u = _make_user(portal_name="OldName", ai_designation="Sub #01", ai_identity_locked=True)
    with pytest.raises(ValueError, match="зафиксировано алгоритмом ИИ"):
        update_user_identity(u, portal_name="ChangedName", is_ai_action=False)

    # But AI action is permitted
    update_user_identity(u, portal_name="AINewName", is_ai_action=True)
    assert u.portal_name == "AINewName"


def test_ai_assign_identity():
    u = _make_user(portal_name=None, ai_designation=None, ai_identity_locked=False)
    ai_assign_identity(u, portal_name="Искра", ai_designation="Sub #42", reason="Присвоено за дисциплину", lock=True)
    assert u.portal_name == "Искра"
    assert u.ai_designation == "Sub #42"
    assert u.ai_identity_locked is True
    assert u.ai_status_reason == "Присвоено за дисциплину"


def test_status_tags_management():
    u = _make_user()
    add_status_tag(u, "collared", category="permanent")
    add_status_tag(u, "chastity_locked", category="standing")
    add_status_tag(u, "#good_pet", category="dynamic")

    assert has_status_tag(u, "collared", category="permanent")
    assert has_status_tag(u, "chastity_locked")
    assert has_status_tag(u, "good_pet")

    active = get_active_tags(u)
    assert "#collared" in active
    assert "#chastity_locked" in active
    assert "#good_pet" in active

    remove_status_tag(u, "good_pet", category="dynamic")
    assert not has_status_tag(u, "good_pet")


def test_wear_reactive_triggers():
    u = _make_user()
    on_wear_status_change(u, is_locked=True)
    assert has_status_tag(u, "chastity_locked", category="standing")

    on_wear_breached(u)
    assert has_status_tag(u, "breached", category="dynamic")
    assert has_status_tag(u, "punished", category="dynamic")
    assert not has_status_tag(u, "good_pet", category="dynamic")

    on_wear_checkin_success(u)
    assert has_status_tag(u, "good_pet", category="dynamic")
    assert not has_status_tag(u, "breached", category="dynamic")

    on_wear_status_change(u, is_locked=False)
    assert not has_status_tag(u, "chastity_locked", category="standing")


@pytest.mark.asyncio
async def test_profile_page_integration(auth_client, db_session, test_user):
    # 1. GET /profile renders successfully with role fields
    resp = await auth_client.get("/profile")
    assert resp.status_code == 200
    html = resp.text
    assert "Ролевой профиль и статус" in html
    assert "Имя на портале" in html

    # 2. POST /profile/update saves role identity fields
    data = {
        "display_name": "New Display Name",
        "locale": "ru",
        "timezone": "Europe/Moscow",
        "portal_name": "ПортальноеИмя",
        "ai_designation": "Sub #77",
        "primary_role": "submissive",
        "portal_roles": ["pet", "chastity_captive"],
        "physiology": "female",
    }
    post_resp = await auth_client.post("/profile/update", data=data, follow_redirects=False)
    assert post_resp.status_code == 303
    assert "status=updated" in post_resp.headers["location"]

    await db_session.refresh(test_user)
    assert test_user.portal_name == "ПортальноеИмя"
    assert test_user.ai_designation == "Sub #77"
    assert test_user.primary_role == "submissive"
    assert "pet" in test_user.portal_roles
    assert test_user.physiology == "female"

