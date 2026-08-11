"""Seed data: 16 top-level activity categories with subcategories (ADR-035).

Based on ``examples/update.md``. Categories are neutral reference data —
independent of concrete objects and numeric values. Idempotent: skips
categories whose slug already exists.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import ActivityCategory

# (slug, title, description, [subcategories: (slug, title, description)])
SEED_CATEGORIES: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
    (
        "fluid_control",
        "Контроль жидкостей",
        "Туалетный контроль, удержание, циклы, клизмы, связанные варианты.",
        [
            ("fluid_toilet_control", "Туалетный контроль", "Контроль посещений туалета и режима."),
            ("fluid_retention", "Удержание", "Удержание и режим потребления."),
            ("fluid_cycles", "Циклы", "Циклы потребления/выделения."),
            ("fluid_enemas", "Клизмы", "Клизмы и связанные практики."),
        ],
    ),
    (
        "scat_play",
        "Скат-практики",
        "Скат-практики. Не смешивать с контролем жидкостей.",
        [],
    ),
    (
        "breath_restriction",
        "Ограничение дыхания",
        "Отдельная верхнеуровневая категория, не модификатор других практик.",
        [],
    ),
    (
        "oral_anal_friction",
        "Фрикции и техника",
        "Оральные, анальные, глубина, ритм, позиции, темп, удержание позиции.",
        [
            ("friction_oral", "Оральные", "Оральные техники."),
            ("friction_anal", "Анальные", "Анальные техники."),
            ("friction_depth", "Глубина", "Глубина и контроль."),
            ("friction_rhythm", "Ритм и темп", "Ритм, темп, удержание позиции."),
        ],
    ),
    (
        "wearables_chastity",
        "Ношение и целомудрие",
        "Клетка, пробки, кляпы, зажимы, бельё, аксессуары, длительное ношение.",
        [
            ("wear_chastity_cage", "Клетка", "Клетки целомудрия."),
            ("wear_plugs", "Пробки", "Анальные пробки."),
            ("wear_gags", "Кляпы", "Кляпы."),
            ("wear_clamps", "Зажимы", "Зажимы."),
            ("wear_lingerie", "Бельё", "Бельё."),
            ("wear_longterm", "Длительное ношение", "Длительное ношение."),
        ],
    ),
    (
        "bondage_restraint",
        "Фиксация и бондаж",
        "Верёвки, манжеты, положения, stress positions, cage/kennel, плёнка, подвесные варианты.",
        [
            ("bondage_rope", "Верёвки", "Верёвочный бондаж."),
            ("bondage_cuffs", "Манжеты", "Манжеты и наручники."),
            ("bondage_positions", "Положения", "Положения тела."),
            ("bondage_stress", "Stress positions", "Напряжённые позы."),
            ("bondage_cage", "Cage / kennel", "Клетки и вольеры."),
            ("bondage_wrap", "Плёнка", "Плёнка и упаковка."),
            ("bondage_suspension", "Подвесные варианты", "Подвесной бондаж."),
        ],
    ),
    (
        "sensation",
        "Сенсорика",
        "Температура, текстуры, вибрация, электрические устройства, щекотка, "
        "депривация, вакуум, другие сенсорные воздействия.",
        [
            ("sensation_temperature", "Температура", "Тепло и холод."),
            ("sensation_textures", "Текстуры", "Материалы и фактуры."),
            ("sensation_vibration", "Вибрация", "Вибраторы и вибро."),
            ("sensation_electric", "Электро", "Электрические устройства."),
            ("sensation_tickle", "Щекотка", "Щекотка."),
            ("sensation_deprivation", "Депривация", "Сенсорная депривация."),
            ("sensation_vacuum", "Вакуум", "Вакуумные устройства."),
        ],
    ),
    (
        "impact_cbt",
        "Ударные практики и CBT",
        "Руки, ремень, паддл, cane, flogger, single-tail, trampling, bastinado, воздействие на грудь и гениталии.",
        [
            ("impact_hand", "Руки", "Удары рукой."),
            ("impact_belt", "Ремень", "Ремень."),
            ("impact_paddle", "Паддл", "Паддл."),
            ("impact_cane", "Cane", "Трость."),
            ("impact_flogger", "Flogger", "Флоггер."),
            ("impact_single_tail", "Single-tail", "Хлыст."),
            ("impact_trampling", "Trampling", "Затаптывание."),
            ("impact_bastinado", "Bastinado", "Бостинадо."),
            ("impact_chest_genitals", "Грудь и гениталии", "Воздействие на грудь и гениталии (CBT)."),
        ],
    ),
    (
        "humiliation_objectification",
        "Унижение и объектность",
        "Вербальные элементы, мантры, body writing, зеркало, позы, статусы, objectification.",
        [
            ("hum_verbal", "Вербальные элементы", "Слова и вербальное унижение."),
            ("hum_mantras", "Мантры", "Мантры и повторения."),
            ("hum_body_writing", "Body writing", "Надписи на теле."),
            ("hum_mirror", "Зеркало", "Работа с зеркалом."),
            ("hum_poses", "Позы", "Демонстрационные позы."),
            ("hum_status", "Статусы", "Статусы и роли."),
            ("hum_objectification", "Objectification", "Объектность."),
        ],
    ),
    (
        "service_protocols",
        "Сервис и обслуживание",
        "Уборка, поручения, обслуживание, human furniture, ритуалы, правила поведения.",
        [
            ("service_cleaning", "Уборка", "Уборка."),
            ("service_errands", "Поручения", "Поручения."),
            ("service_human_furniture", "Human furniture", "Мебель."),
            ("service_rituals", "Ритуалы", "Ритуалы обслуживания."),
            ("service_rules", "Правила поведения", "Правила поведения."),
        ],
    ),
    (
        "control_psychology",
        "Контроль и психологические сценарии",
        "Permission/denial, orgasm control, tease/denial, task queues, гипнотические и ритуальные сценарии.",
        [
            ("control_permission", "Permission / denial", "Разрешения и отказы."),
            ("control_orgasm", "Orgasm control", "Контроль оргазма."),
            ("control_tease", "Tease / denial", "Тиз и отказ."),
            ("control_queues", "Task queues", "Очереди задач."),
            ("control_hypno", "Гипнотические сценарии", "Гипноз и ритуалы."),
        ],
    ),
    (
        "clothing_fetish",
        "Одежда и фетиш-элементы",
        "Латекс, rubber, бельё, колготки, каблуки, компрессионная одежда, униформа, маски.",
        [
            ("clothing_latex", "Латекс", "Латекс."),
            ("clothing_rubber", "Rubber", "Резина."),
            ("clothing_lingerie", "Бельё", "Бельё."),
            ("clothing_hosiery", "Колготки", "Колготки."),
            ("clothing_heels", "Каблуки", "Каблуки."),
            ("clothing_compression", "Компрессионная одежда", "Компрессия."),
            ("clothing_uniform", "Униформа", "Униформа."),
            ("clothing_masks", "Маски", "Маски."),
        ],
    ),
    (
        "roleplay",
        "Ролевые сценарии",
        "Pet play, pony play, doll play, object, prisoner, inspection, training, церемонии, экзамены.",
        [
            ("rp_pet", "Pet play", "Пет-плей."),
            ("rp_pony", "Pony play", "Пони-плей."),
            ("rp_doll", "Doll play", "Кукла."),
            ("rp_object", "Object", "Объект."),
            ("rp_prisoner", "Prisoner", "Заключённый."),
            ("rp_inspection", "Inspection", "Инспекция."),
            ("rp_training", "Training", "Тренировка роли."),
            ("rp_ceremonies", "Церемонии и экзамены", "Церемонии, экзамены."),
        ],
    ),
    (
        "remote_digital",
        "Удалённые и цифровые задания",
        "Команды, отчётность, таймеры, голосовые задания, приватные подтверждения, удалённые ритуалы.",
        [
            ("remote_commands", "Команды", "Удалённые команды."),
            ("remote_reporting", "Отчётность", "Отчётность."),
            ("remote_timers", "Таймеры", "Таймеры."),
            ("remote_voice", "Голосовые задания", "Голосовые задания."),
            ("remote_confirm", "Приватные подтверждения", "Подтверждения."),
            ("remote_rituals", "Удалённые ритуалы", "Удалённые ритуалы."),
        ],
    ),
    (
        "rituals_aftercare",
        "Ритуалы и aftercare",
        "Подготовка, начало сессии, завершение, восстановление, check-in, рефлексия.",
        [
            ("rituals_prep", "Подготовка", "Подготовка."),
            ("rituals_start", "Начало сессии", "Начало."),
            ("rituals_end", "Завершение", "Завершение."),
            ("rituals_recovery", "Восстановление", "Aftercare."),
            ("rituals_checkin", "Check-in", "Проверка состояния."),
            ("rituals_reflection", "Рефлексия", "Рефлексия."),
        ],
    ),
    (
        "session_blocks",
        "Сессионные блоки",
        "Короткая сцена, тематический блок, вечерний сценарий, full-day protocol, "
        "недельный челлендж, progression plan.",
        [
            ("block_short", "Короткая сцена", "Короткая сцена."),
            ("block_themed", "Тематический блок", "Тематический блок."),
            ("block_evening", "Вечерний сценарий", "Вечерний сценарий."),
            ("block_full_day", "Full-day protocol", "Дневной протокол."),
            ("block_weekly", "Недельный челлендж", "Недельный челлендж."),
            ("block_progression", "Progression plan", "План прогрессии."),
        ],
    ),
]


async def seed_categories(db: AsyncSession) -> list[ActivityCategory]:
    """Create top-level categories + subcategories if the table is empty."""
    result = await db.execute(select(ActivityCategory.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return []  # Already seeded

    created: list[ActivityCategory] = []
    for order, (slug, title, description, children) in enumerate(SEED_CATEGORIES):
        parent = ActivityCategory(
            slug=slug,
            title=title,
            description=description,
            sort_order=order,
            is_active=True,
        )
        db.add(parent)
        created.append(parent)
        await db.flush()  # get parent.id

        for c_order, (c_slug, c_title, c_desc) in enumerate(children):
            child = ActivityCategory(
                slug=c_slug,
                title=c_title,
                description=c_desc,
                sort_order=c_order,
                is_active=True,
                parent_id=parent.id,
            )
            db.add(child)
            created.append(child)

    await db.flush()
    return created
