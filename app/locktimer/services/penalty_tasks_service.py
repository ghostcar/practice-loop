"""Penalty Tasks Service (ADR-204).

Selects and assigns disciplinary penalty tasks from the Activity Entity Catalog
with violation mapping (late_return, breach_relapse, task_missed, verification_missed),
modes (random_one vs all), and dynamic parameter escalation.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.locktimer import LockSession
from app.models.task_status import PLANNED
from app.models.user import User

logger = logging.getLogger(__name__)

# Canonical violation types for lock sessions
VIOLATION_TYPES = {
    "any": "Любое нарушение",
    "late_return": "Опоздание возврата / закрытия окна",
    "breach_relapse": "Самовольный срыв / снятие пояса",
    "task_missed": "Пропуск обязательного задания таймера",
    "verification_missed": "Пропуск фотоконтроля / несовпадение пломбы",
    "game_loss": "Полоса неудач в мини-играх",
}


CATEGORY_LABELS: dict[str, str] = {
    "wearing_chastity": "🔒 Ношение пояса / целомудрие",
    "restraint_bondage": "🪢 Бондаж и фиксация",
    "sensory_play": "👁️ Сенсорная депривация",
    "impact_play": "🪵 Ударные практики / порка",
    "fluid_enema_control": "💧 Клизмы и гидроконтроль",
    "toilet_bowel_control": "🚽 Туалетный контроль",
    "breath_restriction": "🫁 Контроль дыхания",
    "consent_communication": "💬 Коммуникация и правила",
    "psychological_control": "🧠 Психологический контроль",
    "sexual_technique": "✨ Сексуальные техники",
    "connection_aftercare": "❤️ Афтеркей и забота",
    "service_protocol": "📋 Служение и дисциплина",
    "sexual_connection": "🔗 Сексуальное взаимодействие",
    "humiliation_objectification": "⛓️ Унижение и послушание",
    "clothing_fetish": "👗 Одежда и фетиш",
    "control_protocol": "⏱️ Протоколы контроля",
    "device_timer": "⏳ Девайсы и таймеры",
    "session_hybrid": "🎲 Комплексные практики",
    "service_care": "🧴 Забота и гигиена",
}


async def list_available_penalty_entities(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Return catalog entities available for penalty assignments (system or user-owned)."""
    stmt = (
        select(Entity)
        .where(
            (Entity.owner_id.is_(None)) | (Entity.owner_id == user_id),
        )
        .order_by(Entity.category, Entity.real_name)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items: list[dict] = []
    for r in rows:
        schema = r.params_schema or {}
        cat = r.category or "general"
        unit = "раз"
        initial_val = 20

        time_cats = (
            "restraint_bondage", "wearing_chastity", "sensory_play",
            "control_protocol", "device_timer", "service_protocol",
        )
        if "unit" in schema:
            unit = schema["unit"]
            initial_val = schema.get("default", initial_val)
        elif cat in time_cats:
            unit = "мин"
            initial_val = 30
        elif cat == "impact_play":
            unit = "ударов"
            initial_val = 20
        elif cat == "fluid_enema_control":
            unit = "мл"
            initial_val = 500
        elif cat == "toilet_bowel_control":
            unit = "мин"
            initial_val = 60
        elif cat in ("service_care", "connection_aftercare"):
            unit = "мин"
            initial_val = 20

        items.append({
            "id": str(r.id),
            "real_name": r.real_name,
            "category": cat,
            "category_label": CATEGORY_LABELS.get(cat, cat.replace("_", " ").title()),
            "default_unit": unit,
            "default_value": initial_val,
        })
    return items


async def assign_penalty_tasks_for_violation(
    db: AsyncSession,
    session: LockSession,
    violation_type: str = "any",
    violation_count: int = 1,
    context: dict | None = None,
) -> list[ActivityLog]:
    """Assign disciplinary tasks to user's Plan based on session discipline policy and catalog items (ADR-204)."""
    policy = session.discipline_policy or {}
    if not policy.get("penalty_tasks_enabled"):
        return []

    user_id = session.owner_id
    now_dt = datetime.now(UTC)
    config = policy.get("penalty_tasks_config") or {}
    mode = config.get("mode", "random_one")  # "random_one" | "all"
    items = config.get("items") or []

    # If no custom items configured, build candidate from all available catalog entities
    if not items:
        stmt = (
            select(Entity)
            .where(
                (Entity.owner_id.is_(None)) | (Entity.owner_id == user_id),
            )
            .limit(20)
        )
        candidates = list((await db.execute(stmt)).scalars().all())
        if candidates:
            chosen = random.choice(candidates)
            c_cat = chosen.category or "general"
            time_cats = ("restraint_bondage", "wearing_chastity", "sensory_play", "control_protocol")
            if c_cat in time_cats:
                c_unit = "мин"
            elif c_cat == "impact_play":
                c_unit = "ударов"
            else:
                c_unit = "раз"
            c_val = 30 if c_unit == "мин" else 20
            items = [{
                "entity_id": str(chosen.id),
                "activity_name": chosen.real_name,
                "violation_type": "any",
                "is_dynamic": True,
                "initial_value": c_val,
                "unit": c_unit,
            }]
        else:
            items = [{
                "entity_id": None,
                "activity_name": "Дисциплинарная отработка за нарушение",
                "violation_type": "any",
                "is_dynamic": True,
                "initial_value": 30,
                "unit": "раз",
            }]

    # Filter items matching this violation type or "any"
    matching_items = [
        it for it in items
        if it.get("violation_type") in (violation_type, "any", None, "")
    ]
    if not matching_items:
        matching_items = items  # fallback to all configured items

    # Select according to mode
    selected_items = [random.choice(matching_items)] if mode == "random_one" else matching_items

    user = await db.get(User, user_id)
    if user:
        from app.services.discipline_engine import calc_effective_multiplier
        engine_mult = calc_effective_multiplier(user)
    else:
        engine_mult = 1.0

    escalation_mult = float(policy.get("escalation_multiplier", 1.5) or 1.5)
    created_tasks: list[ActivityLog] = []

    for it in selected_items:
        ent_id_str = it.get("entity_id")
        ent_uuid = None
        if ent_id_str:
            try:
                ent_uuid = uuid.UUID(str(ent_id_str).strip())
            except ValueError:
                ent_uuid = None

        name = it.get("activity_name") or "Дисциплинарное задание"
        unit = it.get("unit") or "раз"
        try:
            initial_val = int(it.get("initial_value") or 30)
        except (ValueError, TypeError):
            initial_val = 30

        # Scale base value if user has active cross-contour multiplier (> 1.0)
        scaled_base_val = int(round(initial_val * engine_mult)) if engine_mult > 1.0 else initial_val

        is_dynamic = bool(it.get("is_dynamic", True))
        if is_dynamic and violation_count > 1:
            multiplier_factor = escalation_mult ** (violation_count - 1)
            applied_val = int(round(scaled_base_val * multiplier_factor))
            title = f"[Штраф] {name}: {applied_val} {unit} (эскалация #{violation_count} x{escalation_mult})"
        else:
            applied_val = scaled_base_val
            title = f"[Штраф] {name}: {applied_val} {unit}"

        # Schedule deadline 3 hours ahead
        due_at = now_dt + timedelta(hours=3)

        task_log = ActivityLog(
            user_id=user_id,
            entity_id=ent_uuid,
            status=PLANNED,
            title_override=title,
            scheduled_at=now_dt,
            selected_entity_name=name,
            selected_params={
                "value": applied_val,
                "unit": unit,
                "initial_value": initial_val,
                "escalation_count": violation_count,
                "violation_type": violation_type,
            },
            planned_value=f"{applied_val} {unit}",
            points_awarded=0,
            penalty_applied=True,
            penalty_details={
                "source": "locktimer_violation",
                "session_id": str(session.id),
                "violation_type": violation_type,
                "violation_count": violation_count,
                "due_at": due_at.isoformat(),
                "context": context or {},
            },
            created_at=now_dt,
        )
        db.add(task_log)
        created_tasks.append(task_log)

    await db.flush()
    return created_tasks
