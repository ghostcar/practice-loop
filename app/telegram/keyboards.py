"""Telegram Bot keyboards for the Personal Contour.

Provides the persistent main Reply Keyboard and domain-specific Inline keyboards
for tasks, medication slots, AI generator, workouts, health, and progress.
"""

from __future__ import annotations

import uuid
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Persistent bottom Reply Keyboard for quick access to the personal contour."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 План дня"),
                KeyboardButton(text="💊 Лекарства"),
            ],
            [
                KeyboardButton(text="🤖 AI-генератор"),
                KeyboardButton(text="🏋️ Тренировка"),
            ],
            [
                KeyboardButton(text="❤️ Чек-ин / Замеры"),
                KeyboardButton(text="🏆 Прогресс"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def get_task_card_keyboard(log_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Inline action buttons for an active task card."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено (1 клик)", callback_data=f"done:{log_id}"),
            ],
            [
                InlineKeyboardButton(text="⚙️ С параметрами", callback_data=f"task_custom:{log_id}"),
                InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"task_skip:{log_id}"),
            ],
            [
                InlineKeyboardButton(text="⏹ Прервать со штрафом", callback_data=f"int:{log_id}"),
            ],
        ]
    )


def get_ai_generator_keyboard() -> InlineKeyboardMarkup:
    """Presets for AI activity generation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎲 AI автоподбор (1 клик)", callback_data="ai_gen:auto"),
            ],
            [
                InlineKeyboardButton(text="⚡ Короткая (10–15 мин)", callback_data="ai_gen:quick"),
                InlineKeyboardButton(text="🧘 Лёгкая / Релакс", callback_data="ai_gen:relax"),
            ],
            [
                InlineKeyboardButton(text="🔥 Интенсивная", callback_data="ai_gen:intense"),
                InlineKeyboardButton(text="📋 План дня", callback_data="nav_tasks"),
            ],
        ]
    )


def get_med_slot_keyboard(
    slot_key: str,
    slot_time: str,
    individual_items: list[dict[str, Any]] | None = None,
) -> InlineKeyboardMarkup:
    """Action keyboard for a medication time slot."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"✅ Принять всё ({slot_time})",
                callback_data=f"med_slot_take:{slot_key}:{slot_time}",
            )
        ]
    ]

    if individual_items:
        for it in individual_items[:4]:
            sched_id = it.get("schedule_id") or it.get("id")
            name = it.get("medication_name", "Препарат")[:20]
            if sched_id:
                rows.append([
                    InlineKeyboardButton(
                        text=f"💊 Принять {name}",
                        callback_data=f"med_take:{sched_id}",
                    )
                ])

    rows.append([
        InlineKeyboardButton(text="📸 Сканировать пачку", callback_data="med_scan_guide"),
        InlineKeyboardButton(text="📦 Аптечки и остатки", callback_data="med_kits_view"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_training_keyboard(
    day_id: uuid.UUID,
    subtasks: list[dict[str, Any]] | None = None,
    is_completed: bool = False,
) -> InlineKeyboardMarkup:
    """Action keyboard for today's workout."""
    rows: list[list[InlineKeyboardButton]] = []

    if subtasks and not is_completed:
        for idx, st in enumerate(subtasks[:6]):
            is_done = st.get("is_done", False)
            title = st.get("desc") or st.get("title") or f"Упражнение {idx + 1}"
            icon = "✅" if is_done else "⏳"
            rows.append([
                InlineKeyboardButton(
                    text=f"{icon} {title[:28]}",
                    callback_data=f"tr_toggle:{day_id}:{idx}",
                )
            ])

    action_row: list[InlineKeyboardButton] = []
    if not is_completed:
        action_row.append(
            InlineKeyboardButton(text="✅ Завершить тренировку", callback_data=f"tr_complete:{day_id}")
        )
    action_row.append(
        InlineKeyboardButton(text="🤖 Адаптировать (AI)", callback_data=f"tr_adapt:{day_id}")
    )
    rows.append(action_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_health_keyboard(
    mood: int | None = None,
    energy: int | None = None,
) -> InlineKeyboardMarkup:
    """Action keyboard for daily health check-in."""
    mood_row: list[InlineKeyboardButton] = []
    for i in range(1, 6):
        label = f"⭐{i}" if mood == i else str(i)
        mood_row.append(InlineKeyboardButton(text=label, callback_data=f"health_mood:{i}"))

    energy_row: list[InlineKeyboardButton] = []
    for i in range(1, 6):
        label = f"⚡{i}" if energy == i else str(i)
        energy_row.append(InlineKeyboardButton(text=label, callback_data=f"health_energy:{i}"))

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="— Настроение (1-5) —", callback_data="noop")],
            mood_row,
            [InlineKeyboardButton(text="— Энергия (1-5) —", callback_data="noop")],
            energy_row,
            [
                InlineKeyboardButton(text="⚖️ Записать вес", callback_data="health_weight_prompt"),
                InlineKeyboardButton(text="🌸 Фаза цикла", callback_data="health_cycle_view"),
            ],
            [
                InlineKeyboardButton(text="🧴 Уход & Процедуры", callback_data="health_care_view"),
            ],
        ]
    )


def get_stats_keyboard(has_penalties: bool = False) -> InlineKeyboardMarkup:
    """Action keyboard for user statistics and progress."""
    rows: list[list[InlineKeyboardButton]] = []
    if has_penalties:
        rows.append([
            InlineKeyboardButton(text="🔄 Отработать штраф", callback_data="stat_redemptions")
        ])

    rows.append([
        InlineKeyboardButton(text="🎯 Квесты дня", callback_data="stat_quests"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="stat_refresh"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)
