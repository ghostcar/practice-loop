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
        add_status_tag(user, "in_lock_cycle", "standing")
    else:
        remove_status_tag(user, "chastity_locked", "standing")
        remove_status_tag(user, "in_lock_cycle", "standing")


def on_timer_frozen(user: User) -> None:
    """Reactive trigger: lock timer permanently frozen (time halted)."""
    add_status_tag(user, "frozen_timer", "standing")
    remove_status_tag(user, "thawed", "dynamic")


def on_timer_unfrozen(user: User) -> None:
    """Reactive trigger: lock timer unfreezed (time resumed)."""
    remove_status_tag(user, "frozen_timer", "standing")
    add_status_tag(user, "thawed", "dynamic")


def on_pillory_status(user: User, is_pilloried: bool) -> None:
    """Reactive trigger: pillory status change."""
    if is_pilloried:
        add_status_tag(user, "pilloried", "standing")
    else:
        remove_status_tag(user, "pilloried", "standing")


def on_challenge_outcome(user: User, success: bool) -> None:
    """Reactive trigger: obedience challenge result."""
    remove_status_tag(user, "under_trial", "dynamic")
    if success:
        add_status_tag(user, "obedient", "dynamic")
        remove_status_tag(user, "disobedient", "dynamic")
        # Completing challenge grants fortune redemption
        remove_status_tag(user, "unlucky", "dynamic")
        remove_status_tag(user, "loser", "standing")
    else:
        add_status_tag(user, "disobedient", "dynamic")
        remove_status_tag(user, "obedient", "dynamic")


def on_challenge_started(user: User) -> None:
    """Reactive trigger: obedience challenge initiated."""
    add_status_tag(user, "under_trial", "dynamic")


def on_session_finished(user: User, is_safety_stop: bool = False) -> None:
    """Reactive trigger: lock session termination."""
    remove_status_tag(user, "chastity_locked", "standing")
    remove_status_tag(user, "in_lock_cycle", "standing")
    remove_status_tag(user, "frozen_timer", "standing")
    remove_status_tag(user, "pilloried", "standing")
    remove_status_tag(user, "under_trial", "dynamic")
    if is_safety_stop:
        add_status_tag(user, "broken_lock", "dynamic")
        add_status_tag(user, "punished", "dynamic")
    else:
        add_status_tag(user, "lock_survived", "dynamic")


def process_game_bad_luck(
    user: User,
    *,
    is_bad: bool,
    is_jackpot: bool = False,
    current_streak: int = 0,
) -> tuple[int, list[str]]:
    """Track bad luck streaks in Wheel & Dice, escalating loser statuses (ADR-200).

    Returns:
        (new_streak, list_of_newly_awarded_tag_names)
    """
    if is_bad:
        new_streak = current_streak + 1
        newly_awarded: list[str] = []

        if new_streak == 2:
            add_status_tag(user, "unlucky", "dynamic")
            newly_awarded.append("#unlucky")
        elif new_streak == 3:
            add_status_tag(user, "loser", "standing")
            newly_awarded.append("#loser")
        elif new_streak >= 4:
            add_status_tag(user, "pathetic_loser", "permanent")
            newly_awarded.append("#pathetic_loser")

        return new_streak, newly_awarded

    # Luck / mercy / neutral outcome resets streak
    if is_jackpot:
        remove_status_tag(user, "unlucky", "dynamic")
        remove_status_tag(user, "loser", "standing")
    else:
        remove_status_tag(user, "unlucky", "dynamic")

    return 0, []


async def notify_status_escalation(user: User, newly_awarded: list[str], streak: int) -> None:
    """Send asynchronous Telegram notification about status tag escalation (ADR-201)."""
    if not newly_awarded or not getattr(user, "telegram_chat_id", None):
        return
    import contextlib

    from app.telegram.bot import send_telegram_notification
    tag_str = " ".join(newly_awarded)
    text = (
        f"⚠️ **Эскалация статуса в сессии пояса!**\n\n"
        f"Серия неудач достигла **{streak}** подряд.\n"
        f"Вам присвоен статус: **{tag_str}**!\n\n"
        f"Выполните испытание послушания или выбейте джекпот для искупления."
    )
    with contextlib.suppress(Exception):
        await send_telegram_notification(user.telegram_chat_id, text)
