"""Personal Contour — User Status & Roles (ADR-196, ADR-200, ADR-201)."""

from __future__ import annotations

import contextlib

from aiogram import F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database import async_session_factory
from app.models.user import User
from app.services import wear_reactive_service as wear_svc
from app.services.identity_registry import PORTAL_ROLES, PRIMARY_ROLES
from app.services.identity_service import get_effective_display_name
from app.telegram.pc.helpers import TAG_TITLES_RU, _get_user_by_chat, personal_router


def _render_user_status_card(user: User, status: dict | None = None) -> tuple[str, InlineKeyboardMarkup]:
    """Renders comprehensive user identity and status card with tags breakdown."""
    lines = ["👤 **Профиль и статус участника**\n"]
    display_name = get_effective_display_name(user)
    lines.append(f"• **Имя:** {display_name}")
    if user.portal_name and user.portal_name != display_name:
        lines.append(f"• **Портальное имя:** {user.portal_name}")
    if user.ai_designation:
        lines.append(f"• **Реестровый индекс ИИ:** `#{user.ai_designation}`")

    primary_key = user.primary_role or "submissive"
    primary_title = PRIMARY_ROLES.get(primary_key, {}).get("title_ru", "Ведомый / Нижний")
    lines.append(f"• **Основная роль:** {primary_title}")

    portal_roles = user.portal_roles or []
    if portal_roles:
        pr_titles = [PORTAL_ROLES.get(r, {}).get("title_ru", r) for r in portal_roles]
        lines.append(f"• **Контекстные роли:** {', '.join(pr_titles)}")

    raw_tags = user.status_tags or {}
    perm_tags = raw_tags.get("permanent", [])
    stand_tags = raw_tags.get("standing", [])
    dyn_tags = raw_tags.get("dynamic", [])

    lines.append("\n🏷 **Статус-теги:**")
    if perm_tags:
        perm_formatted = [f"`#{t}` ({TAG_TITLES_RU.get(t, t)})" for t in perm_tags]
        lines.append(f"👑 **Постоянные:** {', '.join(perm_formatted)}")
    if stand_tags:
        stand_formatted = [f"`#{t}` ({TAG_TITLES_RU.get(t, t)})" for t in stand_tags]
        lines.append(f"⏳ **Сессионные:** {', '.join(stand_formatted)}")
    if dyn_tags:
        dyn_formatted = [f"`#{t}` ({TAG_TITLES_RU.get(t, t)})" for t in dyn_tags]
        lines.append(f"⚡ **Динамические:** {', '.join(dyn_formatted)}")

    if not (perm_tags or stand_tags or dyn_tags):
        lines.append("_Активных статус-тегов пока нет._")

    if status and status.get("is_active"):
        session = status.get("session")
        ext = dict(session.extensions_state or {}) if session else {}
        streak = ext.get("bad_luck_streak", 0)
        state_label = (
            "❄️ ЗАМОРОЖЕН"
            if (session and session.is_frozen)
            else ("🟢 ЗАПЕРТ" if status.get("is_locked") else "🔴 СНЯТ")
        )
        lines.append(f"• Состояние: {state_label}")

        lines.append(f"• Таймер: {status['time_text']}")
        if status.get("current_tag"):
            lines.append(f"• Пломба: `#{status['current_tag']}`")
        if streak >= 2:
            lines.append(f"• ⚠️ Серия неудач в играх: **{streak}** подряд!")
        if ext.get("active_challenge"):
            ch = ext["active_challenge"]
            lines.append(f"• 🎭 Испытание: *{ch.get('title')}* (код `{ch.get('verification_code')}`)")
    else:
        lines.append("\n🔒 **Пояс верности:** ношение не активно.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔒 К поясу", callback_data="wear_refresh"),
            InlineKeyboardButton(text="🔄 Обновить статус", callback_data="status_refresh"),
        ]
    ])
    return "\n".join(lines), kb


@personal_router.message(Command("status"))
@personal_router.message(F.text.in_(["Статус", "Мой статус", "/profile", "Профиль"]))
async def msg_user_status(message: types.Message):
    user = await _get_user_by_chat(message.chat.id)
    if user is None:
        await message.answer(
            "🔒 Для просмотра статуса привяжите аккаунт через /link `КОД`",
            parse_mode="Markdown",
        )
        return

    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)

    text, kb = _render_user_status_card(user, status)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@personal_router.callback_query(F.data == "status_refresh")
async def cb_status_refresh(callback: types.CallbackQuery):
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        return
    async with async_session_factory() as db:
        status = await wear_svc.get_wear_status(db, user.id)
    text, kb = _render_user_status_card(user, status)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer("Статус обновлен")
