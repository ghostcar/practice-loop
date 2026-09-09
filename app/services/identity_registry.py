from __future__ import annotations

from typing import Any

# Primary role archetypes (ADR-196)
PRIMARY_ROLES: dict[str, dict[str, Any]] = {
    "submissive": {
        "key": "submissive",
        "title_ru": "Ведомый / Нижний",
        "title_en": "Submissive",
        "description_ru": "Базовый ролевой профиль с готовностью к исполнению регламентов и заданий.",
        "description_en": "Base role archetype oriented on task adherence and directives.",
    },
    "dominant": {
        "key": "dominant",
        "title_ru": "Ведущий / Верхний",
        "title_en": "Dominant",
        "description_ru": "Направляющий ролевой профиль с фокусом на регламенты и контроль.",
        "description_en": "Guiding role archetype with control and supervision privileges.",
    },
    "keyholder": {
        "key": "keyholder",
        "title_ru": "Ключник / Контроллер",
        "title_en": "Keyholder",
        "description_ru": "Специализация контроля замков, таймеров и ограничений.",
        "description_en": "Specialization in lock timing, devices, and access management.",
    },
    "switch": {
        "key": "switch",
        "title_ru": "Переключаемый",
        "title_en": "Switch",
        "description_ru": "Гибкий профиль с чередованием ведущей и ведомой ролей.",
        "description_en": "Adaptive role alternating between guided and guiding behaviors.",
    },
    "sissy": {
        "key": "sissy",
        "title_ru": "Трансформационный профиль",
        "title_en": "Transformational / Sissy",
        "description_ru": "Специализированная роль с фокусом на уход, феминизацию и эстетику.",
        "description_en": "Specialized role emphasizing aesthetics, care routines, and expression.",
    },
    "master_mistress": {
        "key": "master_mistress",
        "title_ru": "Старший распорядитель",
        "title_en": "Master / Mistress",
        "description_ru": "Полное управление протоколами и делегированными правами участников.",
        "description_en": "Full administrative authority over protocols and participant regimens.",
    },
}

# Contextual secondary roles (ADR-196)
PORTAL_ROLES: dict[str, dict[str, Any]] = {
    "pet": {
        "key": "pet",
        "title_ru": "Питомец",
        "title_en": "Pet",
        "category": "service",
    },
    "chastity_captive": {
        "key": "chastity_captive",
        "title_ru": "Носитель пояса",
        "title_en": "Chastity Captive",
        "category": "restriction",
    },
    "pain_slut": {
        "key": "pain_slut",
        "title_ru": "Мазохистический профиль",
        "title_en": "Endurance / Sensation",
        "category": "sensation",
    },
    "slave": {
        "key": "slave",
        "title_ru": "Слуга / Подчинённый",
        "title_en": "Devoted Sub / Slave",
        "category": "devotion",
    },
    "slut": {
        "key": "slut",
        "title_ru": "Игровой / Эротический профиль",
        "title_en": "Sensual Profile",
        "category": "sensual",
    },
    "sissy_maid": {
        "key": "sissy_maid",
        "title_ru": "Горничная / Сервисный профиль",
        "title_en": "Service Maid",
        "category": "service",
    },
    "brat": {
        "key": "brat",
        "title_ru": "Бунтарь / Провокатор",
        "title_en": "Brat",
        "category": "dynamic",
    },
    "service_sub": {
        "key": "service_sub",
        "title_ru": "Сервисный исполнитель",
        "title_en": "Service Submissive",
        "category": "service",
    },
    "switch": {
        "key": "switch",
        "title_ru": "Смешанный профиль",
        "title_en": "Switch Profile",
        "category": "adaptive",
    },
    "observer": {
        "key": "observer",
        "title_ru": "Наблюдатель",
        "title_en": "Observer",
        "category": "monitoring",
    },
}

# Role compatibility matrix: primary_role -> set of allowed portal_roles
ROLE_COMPATIBILITY: dict[str, set[str]] = {
    "submissive": {
        "pet",
        "chastity_captive",
        "pain_slut",
        "slave",
        "slut",
        "sissy_maid",
        "brat",
        "service_sub",
        "switch",
        "observer",
    },
    "sissy": {
        "pet",
        "chastity_captive",
        "pain_slut",
        "slave",
        "slut",
        "sissy_maid",
        "brat",
        "service_sub",
        "switch",
        "observer",
    },
    "switch": set(PORTAL_ROLES.keys()),
    "dominant": {"observer", "switch"},
    "keyholder": {"observer", "switch", "chastity_captive"},
    "master_mistress": {"observer", "switch"},
}

# Default status tags taxonomy (ADR-196)
DEFAULT_STATUS_TAGS: dict[str, list[dict[str, str]]] = {
    "permanent": [
        {"tag": "collared", "title_ru": "Носит ошейник", "title_en": "Collared"},
        {"tag": "owned", "title_ru": "Принадлежит", "title_en": "Owned"},
        {"tag": "masochist", "title_ru": "Мазохист", "title_en": "Masochist"},
        {"tag": "devoted", "title_ru": "Преданный", "title_en": "Devoted"},
        {"tag": "sensory_seeker", "title_ru": "Сенсорный искатель", "title_en": "Sensory Seeker"},
    ],
    "standing": [
        {"tag": "chastity_locked", "title_ru": "Заперт в поясе", "title_en": "Chastity Locked"},
        {"tag": "probation", "title_ru": "Испытательный срок", "title_en": "Probation"},
        {"tag": "training_cycle", "title_ru": "В цикле тренировок", "title_en": "Training Cycle"},
        {"tag": "diet_regimen", "title_ru": "На диет-режиме", "title_en": "Diet Regimen"},
        {"tag": "med_course", "title_ru": "На курсе препаратов", "title_en": "Medication Course"},
    ],
    "dynamic": [
        {"tag": "punished", "title_ru": "Оштрафован", "title_en": "Punished"},
        {"tag": "denied", "title_ru": "В воздержании", "title_en": "Denied"},
        {"tag": "good_pet", "title_ru": "Послушный", "title_en": "Good Pet"},
        {"tag": "debtor", "title_ru": "Должник по заданиям", "title_en": "Task Debtor"},
        {"tag": "breached", "title_ru": "Нарушил регламент", "title_en": "Regimen Breached"},
        {"tag": "rewarded", "title_ru": "Поощрён", "title_en": "Rewarded"},
        {"tag": "relieved", "title_ru": "Освобождён", "title_en": "Relieved"},
    ],
}

# Physiology classification (ADR-196)
PHYSIOLOGY_TYPES: dict[str, dict[str, str]] = {
    "male": {
        "key": "male",
        "title_ru": "Мужская (XY)",
        "title_en": "Male (XY)",
        "description_ru": "Расчет основного обмена по мужской формуле, мужская анатомия инвентаря.",
    },
    "female": {
        "key": "female",
        "title_ru": "Женская (XX)",
        "title_en": "Female (XX)",
        "description_ru": "Расчет метаболизма по женской формуле, учет менструального цикла и женской анатомии.",
    },
    "intersex": {
        "key": "intersex",
        "title_ru": "Интерсекс / Индивидуальная",
        "title_en": "Intersex / Custom",
        "description_ru": "Индивидуальная настройка расчетных коэффициентов без жестких анатомических рамок.",
    },
}
