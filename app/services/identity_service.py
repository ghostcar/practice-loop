from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.identity_registry import (
    PHYSIOLOGY_TYPES,
    PRIMARY_ROLES,
    ROLE_COMPATIBILITY,
)

if TYPE_CHECKING:
    from app.models.user import User


def get_effective_display_name(user: User, discretion_active: bool = False) -> str:
    """Return effective user name depending on discretion mode and role profile."""
    if discretion_active:
        return user.display_name or "Пользователь"

    if user.portal_name:
        if user.ai_designation:
            return f"{user.portal_name} ({user.ai_designation})"
        return user.portal_name

    return user.display_name or "Пользователь"


def get_addressing_title(user: User, form: str = "neutral", discretion_active: bool = False) -> str:
    """Return conversational title or greeting address for the user."""
    base_name = get_effective_display_name(user, discretion_active=discretion_active)
    if discretion_active:
        return base_name

    p_name = user.portal_name or user.display_name or "Пользователь"

    if form == "formal":
        role_info = PRIMARY_ROLES.get(user.primary_role, {})
        role_label = role_info.get("title_ru", "Участник")
        return f"{role_label} {base_name}"

    if form == "directive":
        desig = user.ai_designation or "Объект"
        return f"[{desig}] {p_name}"

    if form == "affectionate":
        if "pet" in (user.portal_roles or []):
            return f"Хороший {p_name}"
        return p_name

    return base_name


def validate_portal_roles(primary_role: str, portal_roles: list[str]) -> list[str]:
    """Validate and filter portal roles against primary role compatibility matrix."""
    allowed = ROLE_COMPATIBILITY.get(primary_role, set())
    validated = [r for r in portal_roles if r in allowed]
    return validated


def update_user_identity(
    user: User,
    *,
    portal_name: str | None = None,
    ai_designation: str | None = None,
    primary_role: str | None = None,
    portal_roles: list[str] | None = None,
    physiology: str | None = None,
    is_ai_action: bool = False,
) -> None:
    """Update user identity with AI-lock enforcement and compatibility check."""
    if user.ai_identity_locked and not is_ai_action:
        if portal_name is not None and portal_name.strip() != (user.portal_name or ""):
            raise ValueError("Имя на портале зафиксировано алгоритмом ИИ и не может быть изменено вручную.")
        if ai_designation is not None and ai_designation.strip() != (user.ai_designation or ""):
            raise ValueError("Идентификатор ИИ зафиксирован алгоритмом и не может быть изменен вручную.")

    if primary_role is not None:
        if primary_role not in PRIMARY_ROLES:
            raise ValueError(f"Недопустимая первичная роль: {primary_role}")
        user.primary_role = primary_role

    if portal_roles is not None:
        user.portal_roles = validate_portal_roles(user.primary_role, portal_roles)

    if not user.ai_identity_locked or is_ai_action:
        if portal_name is not None:
            user.portal_name = portal_name.strip() if portal_name.strip() else None
        if ai_designation is not None:
            user.ai_designation = ai_designation.strip() if ai_designation.strip() else None

    if physiology is not None:
        if physiology not in PHYSIOLOGY_TYPES:
            raise ValueError(f"Недопустимый тип физиологии: {physiology}")
        user.physiology = physiology


def ai_assign_identity(
    user: User,
    portal_name: str,
    ai_designation: str,
    reason: str | None = None,
    lock: bool = True,
) -> None:
    """Assign portal name and AI designation by AI decision (ADR-196)."""
    update_user_identity(
        user,
        portal_name=portal_name,
        ai_designation=ai_designation,
        is_ai_action=True,
    )
    if reason:
        user.ai_status_reason = reason
    user.ai_identity_locked = lock


def _ensure_tags_dict(user: User) -> dict[str, list[str]]:
    raw = user.status_tags or {}
    tags: dict[str, list[str]] = {
        "permanent": list(raw.get("permanent", [])),
        "standing": list(raw.get("standing", [])),
        "dynamic": list(raw.get("dynamic", [])),
    }
    return tags


def add_status_tag(user: User, tag: str, category: str = "dynamic") -> None:
    """Add status tag to the specified category idempotently."""
    clean_tag = tag.lstrip("#").strip()
    if not clean_tag:
        return
    tags = _ensure_tags_dict(user)
    if category not in tags:
        tags[category] = []
    if clean_tag not in tags[category]:
        tags[category].append(clean_tag)
        user.status_tags = tags


def remove_status_tag(user: User, tag: str, category: str = "dynamic") -> None:
    """Remove status tag from the specified category."""
    clean_tag = tag.lstrip("#").strip()
    tags = _ensure_tags_dict(user)
    if category in tags and clean_tag in tags[category]:
        tags[category].remove(clean_tag)
        user.status_tags = tags


def has_status_tag(user: User, tag: str, category: str | None = None) -> bool:
    """Check whether the user has a specific status tag."""
    clean_tag = tag.lstrip("#").strip()
    tags = _ensure_tags_dict(user)
    if category:
        return clean_tag in tags.get(category, [])
    return any(clean_tag in cat_tags for cat_tags in tags.values())


def get_active_tags(user: User, category: str | None = None) -> list[str]:
    """Return list of formatted active tags (with #)."""
    tags = _ensure_tags_dict(user)
    if category:
        return [f"#{t}" for t in tags.get(category, [])]
    result: list[str] = []
    for cat in ("permanent", "standing", "dynamic"):
        result.extend([f"#{t}" for t in tags.get(cat, [])])
    return result


def on_wear_breached(user: User) -> None:
    """Reactive trigger: wear event breached / late return."""
    add_status_tag(user, "breached", "dynamic")
    add_status_tag(user, "punished", "dynamic")
    remove_status_tag(user, "good_pet", "dynamic")


def on_wear_checkin_success(user: User) -> None:
    """Reactive trigger: regular comfort check-in or clean wear routine."""
    add_status_tag(user, "good_pet", "dynamic")
    remove_status_tag(user, "breached", "dynamic")


def on_wear_status_change(user: User, is_locked: bool) -> None:
    """Reactive trigger: device wear lock state change."""
    if is_locked:
        add_status_tag(user, "chastity_locked", "standing")
    else:
        remove_status_tag(user, "chastity_locked", "standing")
