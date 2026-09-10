"""AI Course Wizard & Drug Interactions service (ADR-207, phase 4).

Features:
- Goal-based course generator (HRT lactation, vitamin complex, joint recovery, sleep/stress, custom).
- LLM prompt generation with deterministic fallback presets.
- 1-click course instantiation with automatic Medication & MedSchedule creation and MedKit binding.
- Drug interactions safety screening (contraindications & time spacing).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import MedCourse, Medication
from app.services.med.course import create_course
from app.services.med.schedule_stock_kit import create_schedule
from app.services.med.substances import sync_med_components

logger = logging.getLogger(__name__)

# ── Предустановленные протоколы (детерминированный оффлайн-шаблон) ───────────

PRESET_PROTOCOLS: dict[str, dict[str, Any]] = {
    "hrt_lactation": {
        "title": "ЗГТ с индукцией лактации (Протокол Ньюмана-Голдфарб / адаптивный)",
        "description": "Поэтапное развитие железистой ткани с последующей активацией рецепторов пролактина.",
        "duration_weeks": 16,
        "cautions": [
            "Требуется мониторинг уровней пролактина и электролитов крови.",
            "Противопоказано при пролактиномах и неконтролируемой гипертонии.",
            "Стимуляция груди (сцеживание) подключается только на фазе активации.",
        ],
        "phases": [
            {
                "phase_name": "Фаза 1: Развитие протоков и альвеол (недели 1-12)",
                "items": [
                    {
                        "med_name": "Эстрадиол (Эстрожель / Дивигель)",
                        "form": "гель",
                        "strength": "0.1%",
                        "dose_quantity": 2.0,
                        "dose_unit": "мг",
                        "frequency_type": "daily",
                        "times_of_day": ["08:00", "20:00"],
                        "food_relation": "independent",
                        "instructions": "Наносить на чистую сухую кожу плеч или бедер, чередуя стороны.",
                    },
                    {
                        "med_name": "Прогестерон микронизированный (Утрожестан / Праджисан)",
                        "form": "капсулы",
                        "strength": "200 мг",
                        "dose_quantity": 1.0,
                        "dose_unit": "капс",
                        "frequency_type": "daily",
                        "times_of_day": ["22:00"],
                        "food_relation": "after_meal",
                        "instructions": "Принимать перед сном для снижения седативного эффекта.",
                    },
                ],
            },
            {
                "phase_name": "Фаза 2: Индукция лактации и стимуляция (недели 13-16)",
                "items": [
                    {
                        "med_name": "Домперидон (Мотилиум / Мотилак)",
                        "form": "таблетки",
                        "strength": "10 мг",
                        "dose_quantity": 1.0,
                        "dose_unit": "таб",
                        "frequency_type": "daily",
                        "times_of_day": ["07:30", "12:30", "18:30"],
                        "food_relation": "before_meal",
                        "meal_offset_min": -30,
                        "instructions": "За 15-30 минут до еды. Контроль ЭКГ при длительном приёме.",
                    },
                    {
                        "med_name": "Лецитин подсолнечный",
                        "form": "капсулы",
                        "strength": "1200 мг",
                        "dose_quantity": 1.0,
                        "dose_unit": "капс",
                        "frequency_type": "daily",
                        "times_of_day": ["08:00", "20:00"],
                        "food_relation": "during_meal",
                        "instructions": "С едой для профилактики лактостазов и текучести протоков.",
                    },
                ],
            },
        ],
    },
    "vitamin_complex": {
        "title": "Сбалансированный комплекс витаминов и микроэлементов",
        "description": "Энергия, иммунитет и поддержка нервной системы с правильным синергетическим таймингом.",
        "duration_weeks": 8,
        "cautions": [
            "Не совмещайте приём цинка и железа в один приём пищи.",
            "Жирорастворимые витамины (D, K, Омега) принимайте с пищей, содержащей полезные жиры.",
        ],
        "phases": [
            {
                "phase_name": "Базовый приём",
                "items": [
                    {
                        "med_name": "Витамин D3 + K2",
                        "form": "капли / капсулы",
                        "strength": "2000 ME",
                        "dose_quantity": 1.0,
                        "dose_unit": "доза",
                        "frequency_type": "daily",
                        "times_of_day": ["08:00"],
                        "food_relation": "during_meal",
                        "instructions": "Утром во время завтрака с жирами.",
                    },
                    {
                        "med_name": "Омега-3 (ЭПК/ДГК)",
                        "form": "капсулы",
                        "strength": "1000 мг",
                        "dose_quantity": 1.0,
                        "dose_unit": "капс",
                        "frequency_type": "daily",
                        "times_of_day": ["08:00"],
                        "food_relation": "during_meal",
                        "instructions": "Во время еды.",
                    },
                    {
                        "med_name": "Магний бисглицинат / хелат",
                        "form": "таблетки",
                        "strength": "200 мг",
                        "dose_quantity": 2.0,
                        "dose_unit": "таб",
                        "frequency_type": "daily",
                        "times_of_day": ["21:30"],
                        "food_relation": "after_meal",
                        "instructions": "Вечером за 30-45 минут до сна для расслабления ЦНС.",
                    },
                ],
            },
        ],
    },
    "joint_recovery": {
        "title": "Хондропротекторный комплекс (Суставы и связки)",
        "description": "Регенерация суставного хряща, связочного аппарата и выработка синовиальной жидкости.",
        "duration_weeks": 12,
        "cautions": [
            "Курс длительный (эффект накопительный, проявляется через 3-4 недели).",
        ],
        "phases": [
            {
                "phase_name": "Основной цикл восстановления",
                "items": [
                    {
                        "med_name": "Коллаген гидролизованный + Витамин C",
                        "form": "порошок / саше",
                        "strength": "5000 мг",
                        "dose_quantity": 1.0,
                        "dose_unit": "порция",
                        "frequency_type": "daily",
                        "times_of_day": ["07:30"],
                        "food_relation": "empty_stomach",
                        "instructions": "Натощак за 30 минут до завтрака, растворив в воде.",
                    },
                    {
                        "med_name": "Глюкозамин + Хондроитин + МСМ",
                        "form": "таблетки",
                        "strength": "комплекс",
                        "dose_quantity": 1.0,
                        "dose_unit": "таб",
                        "frequency_type": "daily",
                        "times_of_day": ["13:00", "19:00"],
                        "food_relation": "during_meal",
                        "instructions": "Во время обеда и ужина, запивая стаканом воды.",
                    },
                ],
            },
        ],
    },
    "stress_sleep": {
        "title": "Антистресс, адаптация и глубокий сон",
        "description": "Снижение кортизолового возбуждения, поддержка фаз медленного сна.",
        "duration_weeks": 4,
        "cautions": [
            "При выраженной сонливости утром снизьте вечернюю дозировку.",
        ],
        "phases": [
            {
                "phase_name": "Курс вечернего восстановления",
                "items": [
                    {
                        "med_name": "L-Теанин",
                        "form": "капсулы",
                        "strength": "200 мг",
                        "dose_quantity": 1.0,
                        "dose_unit": "капс",
                        "frequency_type": "daily",
                        "times_of_day": ["18:00"],
                        "food_relation": "independent",
                        "instructions": "В конце рабочего дня для снятия напряжения без сонливости.",
                    },
                    {
                        "med_name": "Магний L-треонат / Цитрат",
                        "form": "капсулы",
                        "strength": "400 мг",
                        "dose_quantity": 1.0,
                        "dose_unit": "капс",
                        "frequency_type": "daily",
                        "times_of_day": ["22:00"],
                        "food_relation": "independent",
                        "instructions": "За 45 минут до сна.",
                    },
                ],
            },
        ],
    },
}


# ── Известные пары нежелательных взаимодействий препаратов ───────────────────

KNOWN_INTERACTIONS: list[dict[str, Any]] = [
    {
        "keys": [{"спиронолактон", "верошпирон"}, {"калий", "аспаркам", "панангин"}],
        "level": "danger",
        "title": "Риск тяжелой гиперкалиемии",
        "description": (
            "Спиронолактон задерживает калий. Одновременный приём с препаратами калия "
            "опасен нарушениями сердечного ритма."
        ),
    },
    {
        "keys": [{"железо", "феррум", "мальтофер", "сорбифер"}, {"кальций", "магний"}],
        "level": "warning",
        "title": "Конкуренция за всасывание",
        "description": "Кальций и магний блокируют всасывание железа. Разнесите приём минимум на 2-3 часа.",
    },
    {
        "keys": [{"ибупрофен", "нурофен", "кеторол", "диклофенак"}, {"аспирин", "кардиомагнил"}],
        "level": "warning",
        "title": "Повышенный риск раздражения слизистой ЖКТ",
        "description": (
            "Комбинация нескольких НПВС взаимно усиливает побочные эффекты на желудок "
            "без усиления обезболивания."
        ),
    },
]


def check_drug_interactions(med_names: list[str]) -> list[dict[str, Any]]:
    """Проверяет список наименований препаратов на известные конфликты и взаимодействия."""
    names_lower = [n.lower() for n in med_names if n]
    warnings = []
    for rule in KNOWN_INTERACTIONS:
        matched_groups = 0
        matched_names = []
        for group in rule["keys"]:
            for name in names_lower:
                if any(k in name for k in group):
                    matched_groups += 1
                    matched_names.append(name)
                    break
        if matched_groups >= len(rule["keys"]):
            warnings.append({
                "level": rule["level"],
                "title": rule["title"],
                "description": rule["description"],
                "matched_meds": matched_names,
            })
    return warnings


# ── Генерация плана курса ───────────────────────────────────────────────────


async def generate_course_protocol(
    db: AsyncSession,
    user_id: uuid.UUID,
    goal: str,
    custom_prompt: str = "",
) -> dict[str, Any]:
    """Генерирует структурированный план курса на основе пресета или LLM."""
    if goal in PRESET_PROTOCOLS and not custom_prompt.strip():
        preset = PRESET_PROTOCOLS[goal]
        return {
            "course_name": preset["title"],
            "description": preset["description"],
            "duration_weeks": preset["duration_weeks"],
            "cautions": preset["cautions"],
            "phases": preset["phases"],
            "interactions": check_drug_interactions([
                it["med_name"] for p in preset["phases"] for it in p["items"]
            ]),
        }

    # Попытка генерации через LLM
    from app.llm.client import call_llm, set_call_meta
    from app.llm.resolver import resolve_llm_config

    config = await resolve_llm_config(db, user_id, capability="text", section="medication")
    if not config:
        fallback = PRESET_PROTOCOLS.get(goal) or PRESET_PROTOCOLS["vitamin_complex"]
        return {
            "course_name": fallback["title"] + (f" ({custom_prompt[:30]})" if custom_prompt else ""),
            "description": fallback["description"],
            "duration_weeks": fallback["duration_weeks"],
            "cautions": fallback["cautions"],
            "phases": fallback["phases"],
            "interactions": check_drug_interactions([
                it["med_name"] for p in fallback["phases"] for it in p["items"]
            ]),
        }

    # Промпт для LLM
    prompt = (
        f"Ты — опытный врач-фармаколог. Составь индивидуальный курс приёма медикаментов / БАДов.\n"
        f"Цель курса: {goal}.\n"
        f"Уточнения пользователя: {custom_prompt or 'нет'}.\n\n"
        "Сформируй четкий протокол с разделением на фазы или приёмы.\n"
        "Ответ должен быть строго в формате JSON без markdown-блоков: "
        '{"course_name": "Название курса", "description": "Краткое описание стратегии", '
        '"duration_weeks": 8, "cautions": ["Предупреждение 1", "Предупреждение 2"], '
        '"phases": [{"phase_name": "Фаза 1", "items": [{'
        '"med_name": "Название препарата", "form": "таблетки", "strength": "100 мг", '
        '"dose_quantity": 1.0, "dose_unit": "таб", "frequency_type": "daily", '
        '"times_of_day": ["08:00"], "food_relation": "before_meal", "meal_offset_min": -30, '
        '"instructions": "За 30 мин до еды"}]}]}'
    )

    try:
        set_call_meta(section="medication", purpose="course_wizard")
        raw_resp = await call_llm(
            config=config,
            messages=[
                {"role": "system", "content": "You are a clinical pharmacology assistant. Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
            db=db,
            user_id=user_id,
        )
        content = raw_resp.get("content", "").strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(content)
        all_med_names = [it.get("med_name", "") for p in data.get("phases", []) for it in p.get("items", [])]
        data["interactions"] = check_drug_interactions(all_med_names)
        return data
    except Exception as exc:
        logger.warning("LLM course wizard failed: %s, falling back to preset", exc)
        fallback = PRESET_PROTOCOLS.get(goal) or PRESET_PROTOCOLS["vitamin_complex"]
        return {
            "course_name": fallback["title"],
            "description": fallback["description"],
            "duration_weeks": fallback["duration_weeks"],
            "cautions": fallback["cautions"],
            "phases": fallback["phases"],
            "interactions": check_drug_interactions([
                it["med_name"] for p in fallback["phases"] for it in p["items"]
            ]),
        }


# ── Создание курса в БД ─────────────────────────────────────────────────────


async def apply_generated_course(
    db: AsyncSession,
    user_id: uuid.UUID,
    course_data: dict[str, Any],
    kit_id: uuid.UUID | None = None,
) -> MedCourse:
    """Создаёт MedCourse и все MedSchedule для элементов сгенерированного плана."""
    course_name = course_data.get("course_name") or "Новый курс"
    notes = course_data.get("description") or ""
    cautions = course_data.get("cautions", [])
    if cautions:
        notes += "\n\n⚠️ Ограничения и предостережения:\n• " + "\n• ".join(cautions)

    course = await create_course(
        db,
        user_id=user_id,
        name=course_name,
        notes=notes,
    )

    for phase in course_data.get("phases", []):
        phase_name = phase.get("phase_name", "")
        for it in phase.get("items", []):
            med_name = (it.get("med_name") or "").strip()
            if not med_name:
                continue

            existing_med = (
                await db.execute(
                    select(Medication).where(
                        Medication.user_id == user_id,
                        Medication.name.ilike(med_name),
                        Medication.is_active.is_(True),
                    )
                )
            ).scalars().first()

            if not existing_med:
                existing_med = Medication(
                    user_id=user_id,
                    name=med_name,
                    form=it.get("form") or None,
                    strength=it.get("strength") or None,
                    notes=f"Добавлено мастером курсов ({course_name})",
                )
                db.add(existing_med)
                await db.flush()
                await sync_med_components(db, existing_med)

            instr = it.get("instructions") or ""
            if phase_name:
                instr = f"[{phase_name}] {instr}".strip()

            tod = it.get("times_of_day")
            tod_str = ", ".join(tod) if isinstance(tod, list) else str(tod or "08:00")

            await create_schedule(
                db,
                user_id=user_id,
                medication_id=existing_med.id,
                dose_quantity=str(it.get("dose_quantity", 1.0)),
                dose_unit=it.get("dose_unit") or "",
                frequency_type=it.get("frequency_type") or "daily",
                times_per_day=str(len(tod) if isinstance(tod, list) and tod else 1),
                times_of_day=tod_str,
                instructions=instr,
                food_relation=it.get("food_relation") or "independent",
                meal_offset_min=str(it.get("meal_offset_min") or 0),
                preferred_kit_id=str(kit_id) if kit_id else "",
                course_id=course.id,
            )

    await db.commit()
    await db.refresh(course)
    return course
