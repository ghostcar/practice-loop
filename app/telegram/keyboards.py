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
                KeyboardButton(text="🔒 Пояс"),
                KeyboardButton(text="❤️ Чек-ин / Замеры"),
            ],
            [
                KeyboardButton(text="📦 Инвентарь"),
                KeyboardButton(text="⛓️ Позорный столб"),
            ],
            [
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
        ],
        [
            InlineKeyboardButton(text="⏰ Отложить 15 мин", callback_data=f"med_snooze:15:{slot_time}"),
            InlineKeyboardButton(text="⏰ Отложить 30 мин", callback_data=f"med_snooze:30:{slot_time}"),
        ],
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
        InlineKeyboardButton(text="⚡ По требованию (PRN)", callback_data="med_prn_select"),
        InlineKeyboardButton(text="📸 Скан пачки", callback_data="med_scan_guide"),
    ])
    rows.append([
        InlineKeyboardButton(text="📦 Аптечки и остатки", callback_data="med_kits_view"),
        InlineKeyboardButton(text="📥 Пополнить запас", callback_data="med_restock_list"),
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


def get_wear_card_keyboard(
    is_active: bool = True,
    is_locked: bool = False,
    is_agent_mode: bool = False,
    supports_tag: bool = True,
    is_frozen: bool = False,
    has_challenge: bool = False,
) -> InlineKeyboardMarkup:
    """Action keyboard for Open-Ended Wear card with Chaster Extensions."""
    rows: list[list[InlineKeyboardButton]] = []

    if not is_active:
        rows.append([
            InlineKeyboardButton(text="🔒 Надеть и запереть пояс", callback_data="wear_start_init"),
        ])
    elif is_locked:
        rows.append([
            InlineKeyboardButton(text="🔓 Снять пояс", callback_data="wear_unlock_init"),
        ])
        sub_row = []
        if supports_tag:
            sub_row.append(InlineKeyboardButton(text="🔍 Проверка пломбы", callback_data="wear_inspect_init"))
        sub_row.append(InlineKeyboardButton(text="⭐ Комфорт", callback_data="wear_comfort_init"))
        rows.append(sub_row)
    else:
        rows.append([
            InlineKeyboardButton(text="🔒 Запереть пояс", callback_data="wear_relock_init"),
        ])

    rows.append([
        InlineKeyboardButton(text="💥 Отметить оргазм", callback_data="wear_orgasm_init"),
    ])

    if is_active:
        # Мини-игры Chaster Extensions и управление временем (ADR-198, ADR-199, ADR-201)
        game_row: list[InlineKeyboardButton] = [
            InlineKeyboardButton(text="🎡 Колесо", callback_data="wear_game_wheel"),
            InlineKeyboardButton(text="🎲 Кубики", callback_data="wear_game_dice"),
        ]
        if is_frozen:
            game_row.append(InlineKeyboardButton(text="🔥 Разморозить", callback_data="wear_unfreeze"))
        else:
            game_row.append(InlineKeyboardButton(text="❄️ Заморозить", callback_data="wear_freeze"))
        rows.append(game_row)

        if has_challenge:
            rows.append([
                InlineKeyboardButton(text="📸 Сдать фото-испытание", callback_data="wear_challenge_submit"),
                InlineKeyboardButton(text="🏳️ Сдаться", callback_data="wear_challenge_surrender"),
            ])
        else:
            rows.append([
                InlineKeyboardButton(text="🎭 Испытание послушания", callback_data="wear_game_challenge"),
            ])

        rows.append([
            InlineKeyboardButton(text="⏹ Завершить период ношения", callback_data="wear_finish_init"),
        ])

    mode_label = "🤖 Агент: Вкл" if is_agent_mode else "🔘 Агент: Выкл (Кнопки)"
    rows.append([
        InlineKeyboardButton(text=mode_label, callback_data="wear_toggle_agent"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="wear_refresh"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)



def get_wear_device_selection_keyboard(devices: list[Any]) -> InlineKeyboardMarkup:
    """Keyboard for selecting a chastity device / belt from inventory."""
    rows: list[list[InlineKeyboardButton]] = []
    for d in devices:
        props = getattr(d, "extra_properties", None) or {}
        has_tag = True
        if isinstance(props, dict):
            for k in ("supports_tag", "supports_seal", "can_seal", "tag_support", "has_seal", "has_tag"):
                if k in props:
                    val = props[k]
                    if val in (False, "false", 0, "0") or str(val).lower() in ("false", "no", "0"):
                        has_tag = False
                        break
        tag_badge = "🏷 пломба" if has_tag else "🚫 без пломбы"
        status_suffix = " (в работе)" if getattr(d, "inventory_status", None) == "in_use" else ""
        name = d.name[:25]
        btn_text = f"🔒 {name} [{tag_badge}]{status_suffix}"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"wear_dev:{d.id}")])

    rows.append([
        InlineKeyboardButton(text="🔒 Без привязки к инвентарю", callback_data="wear_dev:none"),
    ])
    rows.append([
        InlineKeyboardButton(text="🔙 Отмена", callback_data="wear_refresh"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_wear_reasons_keyboard() -> InlineKeyboardMarkup:
    """Selection of wear unlock reasons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚿 Санитарная обработка (10 мин)", callback_data="wear_reason:hygiene_quick"
                ),
            ],
            [
                InlineKeyboardButton(text="🧴 Уход / Депиляция (60 мин)", callback_data="wear_reason:care_grooming"),
            ],
            [
                InlineKeyboardButton(text="🏃 Спорт / Тренировка (90 мин)", callback_data="wear_reason:sport_workout"),
            ],
            [
                InlineKeyboardButton(text="❤️ Секс / Близость (120 мин)", callback_data="wear_reason:sex_activity"),
            ],
            [
                InlineKeyboardButton(text="🚨 Форс-мажор (Боль / Врач)", callback_data="wear_reason:force_majeure"),
            ],
            [
                InlineKeyboardButton(text="⚠️ Срыв / Нарушение", callback_data="wear_reason:breach_relapse"),
            ],
            [
                InlineKeyboardButton(text="🔙 Отмена", callback_data="wear_refresh"),
            ],
        ]
    )


def get_wear_comfort_keyboard() -> InlineKeyboardMarkup:
    """Selection of physical comfort score (1-5)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 😖", callback_data="wear_score:1"),
                InlineKeyboardButton(text="2 😕", callback_data="wear_score:2"),
                InlineKeyboardButton(text="3 😐", callback_data="wear_score:3"),
                InlineKeyboardButton(text="4 🙂", callback_data="wear_score:4"),
                InlineKeyboardButton(text="5 😊", callback_data="wear_score:5"),
            ],
            [
                InlineKeyboardButton(text="🔙 Отмена", callback_data="wear_refresh"),
            ],
        ]
    )

