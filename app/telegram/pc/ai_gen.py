"""Personal Contour — AI Activity Generator."""

from __future__ import annotations

import logging

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database import async_session_factory
from app.llm.pipeline import generate_task, get_active_llm_config
from app.llm.repair import JsonRepairError
from app.prefs import prefs_from_dict
from app.telegram.keyboards import get_ai_generator_keyboard, get_task_card_keyboard
from app.telegram.pc.helpers import _get_user_by_chat, _require_user, personal_router

logger = logging.getLogger(__name__)


@personal_router.message(F.text.in_(["🤖 AI-генератор", "AI-генератор", "/next", "/generate"]))
async def handle_ai_generator_tab(message: types.Message, state: FSMContext):
    await state.clear()
    user = await _require_user(message)
    if user is None:
        return

    text = (
        "🤖 **AI-генератор персональных практик**\n\n"
        "Искусственный интеллект подбирает активности исключительно из вашего "
        "допустимого каталога (opt-in) на основе недавней истории и баланса нагрузок.\n\n"
        "Выберите готовый пресет или просто напишите мне сообщение с пожеланием "
        "(например: _«Хочу растяжку для спины на 15 минут»_ или _«Подбери расслабляющую практику на вечер»_):"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_ai_generator_keyboard())


@personal_router.callback_query(F.data.startswith("ai_gen:"))
async def cb_ai_generate_task(callback: types.CallbackQuery):
    mode = callback.data.split(":", 1)[1]
    user = await _get_user_by_chat(callback.message.chat.id)
    if user is None:
        await callback.answer("Аккаунт не привязан.", show_alert=True)
        return

    await callback.message.edit_text("🤖 ИИ анализирует ваш профиль и подбирает активность...")
    await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")

    preset_prompts = {
        "quick": "Подбери быструю и эффективную активность длительностью от 10 до 15 минут.",
        "relax": (
            "Подбери мягкую расслабляющую практику низкой интенсивности (1-2 из 5), "
            "направленную на покой и снятие напряжения."
        ),
        "intense": "Подбери активную, стимулирующую практику высокой интенсивности (4-5 из 5).",
        "auto": None,
    }
    user_prompt = preset_prompts.get(mode)

    async with async_session_factory() as db:
        config = await get_active_llm_config(db, user.id)
        if config is None:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="📋 К плану дня", callback_data="nav_tasks")]]
            )
            await callback.message.edit_text(
                "❌ В вашем профиле не настроен активный провайдер LLM.\n"
                "Подключите ключ (Omniroute / OpenRouter / Groq) в настройках на сайте "
                "или выберите портального провайдера.",
                reply_markup=kb,
            )
            return

        try:
            log = await generate_task(
                db=db,
                user_id=user.id,
                llm_config=config,
                session_id=None,
                user_prompt=user_prompt,
                locale=user.locale or "ru",
                llm_mode=prefs_from_dict(user.prefs).llm_mode,
            )
            await db.commit()
        except JsonRepairError:
            await callback.message.edit_text("❌ Ответ ИИ не удалось разобрать. Попробуйте ещё раз.")
            return
        except ValueError as e:
            await callback.message.edit_text(f"❌ {e}")
            return
        except Exception:
            logger.exception("AI generation failed in bot")
            await callback.message.edit_text("❌ Запрос к модели завершился ошибкой. Проверьте настройки LLM.")
            return

    name = log.title_override or log.selected_entity_name or "Практика"
    params = log.selected_params or {}
    cleaned = log.cleaned_response or {}
    reasoning = cleaned.get("reasoning") or params.get("reasoning")

    lines = [
        "🎲 **Новая активность подобрана через AI:**",
        f"🎯 **{name}**",
    ]
    if params.get("duration_min"):
        d_min = params["duration_min"]
        d_max = params.get("duration_max", d_min)
        lines.append(f"⏱ Время: *{d_min}*–*{d_max}* мин")
    if params.get("intensity"):
        lines.append(f"⚡ Интенсивность: *{params['intensity']}/5*")
    if params.get("description"):
        lines.append(f"📝 _{params['description']}_")
    if reasoning:
        lines.append(f"\n💡 *Почему выбрана:* _{reasoning}_")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_task_card_keyboard(log.id),
    )
    await callback.answer("Готово! Активность создана.")
