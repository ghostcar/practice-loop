"""Seed data: catalog entities and LLM provider presets."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import encrypt_api_key
from app.models.entity import Entity
from app.models.llm_config import LLMProviderConfig

# ---------------------------------------------------------------------------
# Seed Entities (30+ tasks from tracker-spec.md §10.5)
# ---------------------------------------------------------------------------

SEED_ENTITIES: list[dict] = [
    # --- Внимание и забота (5) ---
    {
        "type": "one_time",
        "real_name": "Тёплое сообщение-комплимент",
        "category": "Внимание и забота",
        "tags": ["сообщение", "комплимент", "текст"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 1, "max": 5},
            "intensity": {"min": 1, "max": 2, "description": "Уровни: 1-лёгкий → 5-глубокий"},
            "participants": 1,
        },
    },
    {
        "type": "one_time",
        "real_name": "Массаж плеч 10–20 мин",
        "category": "Внимание и забота",
        "tags": ["массаж", "плечи", "расслабление"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 10, "max": 20},
            "intensity": {"min": 1, "max": 4, "description": "Сила нажатия"},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Напиток или угощение партнёру",
        "category": "Внимание и забота",
        "tags": ["напиток", "угощение", "сюрприз"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 5, "max": 15},
            "intensity": {"min": 1, "max": 2},
            "participants": 1,
        },
    },
    {
        "type": "one_time",
        "real_name": "Выслушать о дне без телефона",
        "category": "Внимание и забота",
        "tags": ["слушание", "внимание", "без телефона"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 10, "max": 30},
            "intensity": {"min": 2, "max": 4, "description": "Глубина разговора"},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Мелкий сюрприз в течение дня",
        "category": "Внимание и забота",
        "tags": ["сюрприз", "подарок", "спонтанность"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 5, "max": 15},
            "intensity": {"min": 1, "max": 2},
            "participants": 1,
        },
    },
    # --- Романтика (5) ---
    {
        "type": "one_time",
        "real_name": "Вечер при свечах",
        "category": "Романтика",
        "tags": ["свечи", "вечер", "уют"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 30, "max": 120},
            "intensity": {"min": 2, "max": 5},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Фильм или сериал с обсуждением",
        "category": "Романтика",
        "tags": ["фильм", "сериал", "обсуждение"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 60, "max": 180},
            "intensity": {"min": 1, "max": 3},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Письмо или записка с тёплыми словами",
        "category": "Романтика",
        "tags": ["письмо", "записка", "слова"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 5, "max": 20},
            "intensity": {"min": 2, "max": 4, "description": "Глубина чувств"},
            "participants": 1,
        },
    },
    {
        "type": "one_time",
        "real_name": "Ужин вдвоём без гаджетов",
        "category": "Романтика",
        "tags": ["ужин", "без гаджетов", "вдвоём"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 45, "max": 120},
            "intensity": {"min": 2, "max": 4},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Прогулка за руку 30–60 мин",
        "category": "Романтика",
        "tags": ["прогулка", "за руку", "улица"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 30, "max": 60},
            "intensity": {"min": 1, "max": 2},
            "participants": 2,
        },
    },
    # --- Игры и развлечения (5) ---
    {
        "type": "one_time",
        "real_name": "Настольная игра",
        "category": "Игры и развлечения",
        "tags": ["игра", "настолка", "веселье"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 30, "max": 120},
            "intensity": {"min": 1, "max": 3},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Игра «Вопрос-ответ»",
        "category": "Игры и развлечения",
        "tags": ["вопросы", "ответы", "узнать друг друга"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 15, "max": 45},
            "intensity": {"min": 2, "max": 4, "description": "Откровенность вопросов"},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Совместное хобби 30 мин",
        "category": "Игры и развлечения",
        "tags": ["хобби", "творчество", "совместно"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 30, "max": 60},
            "intensity": {"min": 1, "max": 3},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Викторина друг о друге",
        "category": "Игры и развлечения",
        "tags": ["викторина", "вопросы", "тест"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 10, "max": 30},
            "intensity": {"min": 1, "max": 2},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Парный матч (шахматы/карты)",
        "category": "Игры и развлечения",
        "tags": ["шахматы", "карты", "соревнование"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 15, "max": 90},
            "intensity": {"min": 1, "max": 3},
            "participants": 2,
        },
    },
    # --- Близость и нежность (5) ---
    {
        "type": "one_time",
        "real_name": "Объятия 5–10 мин",
        "category": "Близость и нежность",
        "tags": ["объятия", "нежность", "контакт"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 5, "max": 10},
            "intensity": {"min": 1, "max": 3},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Поцелуйный таймер 60 сек",
        "category": "Близость и нежность",
        "tags": ["поцелуй", "таймер", "нежность"],
        "is_public": True,
        "params_schema": {
            "duration_seconds": {"min": 30, "max": 120},
            "intensity": {"min": 1, "max": 4},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Комплимент + прикосновение",
        "category": "Близость и нежность",
        "tags": ["комплимент", "прикосновение", "контакт"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 1, "max": 5},
            "intensity": {"min": 1, "max": 3},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Совместный душ",
        "category": "Близость и нежность",
        "tags": ["душ", "вода", "вместе"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 10, "max": 25},
            "intensity": {"min": 1, "max": 4},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "15 минут внимания только друг для друга",
        "category": "Близость и нежность",
        "tags": ["внимание", "фокус", "вдвоём"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 15, "max": 15},
            "intensity": {"min": 2, "max": 5},
            "participants": 2,
        },
    },
    # --- Планирование и быт (5) ---
    {
        "type": "one_time",
        "real_name": "План на выходные",
        "category": "Планирование и быт",
        "tags": ["план", "выходные", "организация"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 10, "max": 30},
            "intensity": {"min": 1, "max": 2},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Совместная уборка 30 мин",
        "category": "Планирование и быт",
        "tags": ["уборка", "дом", "совместно"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 30, "max": 60},
            "intensity": {"min": 1, "max": 3},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Список целей на месяц",
        "category": "Планирование и быт",
        "tags": ["цели", "месяц", "планы"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 15, "max": 45},
            "intensity": {"min": 1, "max": 3},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Обсуждение планов",
        "category": "Планирование и быт",
        "tags": ["планы", "обсуждение", "будущее"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 15, "max": 60},
            "intensity": {"min": 2, "max": 4, "description": "Серьёзность тем"},
            "participants": 2,
        },
    },
    {
        "type": "one_time",
        "real_name": "Запланировать вылазку",
        "category": "Планирование и быт",
        "tags": ["вылазка", "путешествие", "план"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 15, "max": 45},
            "intensity": {"min": 1, "max": 2},
            "participants": 2,
        },
    },
    # --- Эксперименты / итерационные (5) ---
    {
        "type": "series",
        "real_name": "Таймер-фазы: удержание 20с → пауза 5с → удержание 30с",
        "category": "Эксперименты",
        "tags": ["таймер", "фазы", "итерации", "удержание"],
        "is_public": True,
        "params_schema": {
            "phases": [
                {"name": "удержание", "duration_seconds": 20},
                {"name": "пауза", "duration_seconds": 5},
                {"name": "удержание", "duration_seconds": 30},
            ],
            "iterations": {"min": 2, "max": 5},
            "intensity": {"min": 1, "max": 4},
            "participants": 2,
        },
    },
    {
        "type": "series",
        "real_name": "Прогрессивная серия из 3 подходов",
        "category": "Эксперименты",
        "tags": ["прогрессия", "подходы", "нарастание"],
        "is_public": True,
        "params_schema": {
            "phases": [
                {"name": "подход 1", "intensity": 1, "duration_seconds": 30},
                {"name": "подход 2", "intensity": 2, "duration_seconds": 30},
                {"name": "подход 3", "intensity": 3, "duration_seconds": 30},
            ],
            "iterations": {"min": 1, "max": 3},
            "participants": 2,
        },
    },
    {
        "type": "series",
        "real_name": "Шкала интенсивности 1→3 за 10 мин",
        "category": "Эксперименты",
        "tags": ["интенсивность", "шкала", "нарастание"],
        "is_public": True,
        "params_schema": {
            "duration_minutes": {"min": 10, "max": 10},
            "intensity_range": {"start": 1, "end": 3},
            "participants": 2,
        },
    },
    {
        "type": "series",
        "real_name": "Циклы со сменой ролей",
        "category": "Эксперименты",
        "tags": ["циклы", "роли", "смена"],
        "is_public": True,
        "params_schema": {
            "roles": ["A", "B"],
            "iterations": {"min": 2, "max": 6},
            "duration_per_cycle_seconds": {"min": 60, "max": 300},
            "participants": 2,
        },
    },
    {
        "type": "series",
        "real_name": "Серия повторов с фиксацией результата",
        "category": "Эксперименты",
        "tags": ["повторы", "фиксация", "результат"],
        "is_public": True,
        "params_schema": {
            "repetitions": {"min": 3, "max": 10},
            "track_result": True,
            "intensity": {"min": 1, "max": 5},
            "participants": 2,
        },
    },
]

# ---------------------------------------------------------------------------
# Seed LLM Presets (Omniroute, Groq, OpenRouter)
# ---------------------------------------------------------------------------

SEED_LLM_PRESETS: list[dict] = [
    {
        "provider_name": "Omniroute",
        "api_base_url": "http://host.docker.internal:20128/v1",
        "api_key": "",  # Omniroute doesn't need a key
        "model_name": "auto",
        "is_active": True,
    },
    {
        "provider_name": "Groq",
        "api_base_url": "https://api.groq.com/openai/v1",
        "api_key": "",  # user fills in
        "model_name": "llama-3.3-70b-versatile",
        "is_active": False,
    },
    {
        "provider_name": "OpenRouter",
        "api_base_url": "https://openrouter.ai/api/v1",
        "api_key": "",  # user fills in
        "model_name": "google/gemini-2.0-flash-001",
        "is_active": False,
    },
]


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------


async def seed_entities(db: AsyncSession, owner_id: uuid.UUID | None = None) -> list[Entity]:
    """Create seed entities if the catalog is empty. Returns created entities."""
    result = await db.execute(select(Entity).limit(1))
    if result.scalar_one_or_none() is not None:
        return []  # Already seeded

    entities = []
    for data in SEED_ENTITIES:
        entity = Entity(
            type=data["type"],
            real_name=data["real_name"],
            category=data["category"],
            tags=data.get("tags"),
            owner_id=owner_id,
            is_public=data["is_public"],
            author_id=owner_id,
            params_schema=data.get("params_schema"),
        )
        db.add(entity)
        entities.append(entity)

    await db.flush()
    return entities


async def seed_llm_presets(db: AsyncSession, user_id: uuid.UUID) -> list[LLMProviderConfig]:
    """Create LLM provider presets for a user if none exist. Returns created configs."""
    result = await db.execute(select(LLMProviderConfig).where(LLMProviderConfig.user_id == user_id).limit(1))
    if result.scalar_one_or_none() is not None:
        return []  # Already seeded

    configs = []
    for data in SEED_LLM_PRESETS:
        encrypted = encrypt_api_key(data["api_key"]) if data["api_key"] else None
        config = LLMProviderConfig(
            user_id=user_id,
            provider_name=data["provider_name"],
            api_base_url=data["api_base_url"],
            api_key_encrypted=encrypted,
            model_name=data["model_name"],
            is_active=data["is_active"],
        )
        db.add(config)
        configs.append(config)

    await db.flush()
    return configs
