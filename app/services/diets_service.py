"""Diets Service — business logic extracted from app.api.diets (thin routes).

Covers: diet CRUD, food-item CRUD, consumption logging, LLM generation/evaluation/synergy,
serializers and page context.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.pipeline import (
    analyze_diet_training_synergy,
    evaluate_diet,
    generate_diet,
    get_active_llm_config,
)
from app.llm.repair import JsonRepairError
from app.models.diet import Diet, DietConsumption, DietEvaluation, DietItem, DietTrainingReview
from app.timeutils import local_today

# ── Allowed diet directions ──
DIET_DIRECTIONS: set[str] = {
    "weight_loss",
    "muscle_gain",
    "health",
    "energy",
    "endurance",
    "general",
    "other",
}


# ═══════════════════════════════════════════════════════════════════════════
# Serializers
# ═══════════════════════════════════════════════════════════════════════════


def item_dict(it: DietItem) -> dict:
    return {
        "id": str(it.id),
        "name": it.name,
        "quantity": it.quantity,
        "unit": it.unit,
        "meal_time": it.meal_time,
        "notes": it.notes,
        "sort_order": it.sort_order,
    }


def diet_dict(d: Diet, with_items: bool = True) -> dict:
    out = {
        "id": str(d.id),
        "name": d.name,
        "direction": d.direction,
        "goal": d.goal,
        "description": d.description,
        "is_active": d.is_active,
        "last_evaluation": d.last_evaluation,
        "evaluated_at": d.evaluated_at.isoformat() if d.evaluated_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
    if with_items:
        out["items"] = [item_dict(i) for i in d.items]
    return out


def consumption_dict(c: DietConsumption) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "quantity": c.quantity,
        "unit": c.unit,
        "meal_time": c.meal_time,
        "diet_id": str(c.diet_id) if c.diet_id else None,
        "consumed_date": c.consumed_date.isoformat(),
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def evaluation_dict(ev: DietEvaluation) -> dict:
    return {
        "id": str(ev.id),
        "score": ev.score,
        "summary": ev.summary,
        "findings": ev.findings or [],
        "applied": ev.applied or [],
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


def review_dict(r: DietTrainingReview) -> dict:
    return {
        "id": str(r.id),
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "analysis": r.analysis,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Page context
# ═══════════════════════════════════════════════════════════════════════════


async def get_diets_page_context(db: AsyncSession, user) -> dict:
    """Build template context for /diets page."""
    from app.timeutils import local_today

    result = await db.execute(
        select(Diet)
        .where(Diet.user_id == user.id)
        .order_by(Diet.is_active.desc(), Diet.created_at.asc())
    )
    diets_list = [diet_dict(d) for d in result.scalars().all()]
    active_config = await get_active_llm_config(db, user.id)
    return {
        "diets": diets_list,
        "active_config": active_config,
        "directions": sorted(DIET_DIRECTIONS),
        "today": local_today().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Diet CRUD
# ═══════════════════════════════════════════════════════════════════════════


async def list_diets(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(Diet)
        .where(Diet.user_id == user_id)
        .order_by(Diet.is_active.desc(), Diet.created_at.asc())
    )
    return [diet_dict(d) for d in result.scalars().all()]


async def create_diet(db: AsyncSession, user_id: uuid.UUID, **kwargs) -> dict:
    diet = Diet(user_id=user_id, **kwargs)
    db.add(diet)
    await db.flush()
    await db.refresh(diet)
    return diet_dict(diet)


async def update_diet(db: AsyncSession, user_id: uuid.UUID, diet_id: uuid.UUID, **kwargs) -> dict:
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user_id))
    diet = result.scalar_one_or_none()
    if not diet:
        raise ValueError("Diet not found")
    for k, v in kwargs.items():
        if v is not None:
            setattr(diet, k, v)
    db.add(diet)
    await db.flush()
    await db.refresh(diet)
    return diet_dict(diet)


async def delete_diet(db: AsyncSession, user_id: uuid.UUID, diet_id: uuid.UUID) -> None:
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user_id))
    diet = result.scalar_one_or_none()
    if not diet:
        raise ValueError("Diet not found")
    await db.delete(diet)


# ═══════════════════════════════════════════════════════════════════════════
# Diet-Item CRUD
# ═══════════════════════════════════════════════════════════════════════════


async def _get_owned_diet(db: AsyncSession, user_id: uuid.UUID, diet_id: uuid.UUID) -> Diet:
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user_id))
    diet = result.scalar_one_or_none()
    if not diet:
        raise ValueError("Diet not found")
    return diet


async def add_diet_item(db: AsyncSession, user_id: uuid.UUID, diet_id: uuid.UUID, **kwargs) -> dict:
    await _get_owned_diet(db, user_id, diet_id)
    max_o = await db.execute(
        select(DietItem.sort_order)
        .where(DietItem.diet_id == diet_id)
        .order_by(DietItem.sort_order.desc())
        .limit(1)
    )
    next_order = (max_o.scalar_one_or_none() or -1) + 1
    item = DietItem(diet_id=diet_id, sort_order=next_order, **kwargs)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item_dict(item)


async def update_diet_item(
    db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, **kwargs
) -> dict:
    result = await db.execute(
        select(DietItem)
        .join(Diet, Diet.id == DietItem.diet_id)
        .where(DietItem.id == item_id, Diet.user_id == user_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise ValueError("Diet item not found")
    for k, v in kwargs.items():
        if v is not None:
            setattr(item, k, v)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item_dict(item)


async def delete_diet_item(
    db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(DietItem)
        .join(Diet, Diet.id == DietItem.diet_id)
        .where(DietItem.id == item_id, Diet.user_id == user_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise ValueError("Diet item not found")
    await db.delete(item)


async def reorder_diet_items(
    db: AsyncSession, user_id: uuid.UUID, diet_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    result = await db.execute(
        select(DietItem)
        .join(Diet, Diet.id == DietItem.diet_id)
        .where(DietItem.diet_id == diet_id, Diet.user_id == user_id)
    )
    items = {i.id: i for i in result.scalars().all()}
    if set(ids) != set(items.keys()):
        raise ValueError("ids must match all items of the diet")
    for pos, iid in enumerate(ids):
        items[iid].sort_order = pos
        db.add(items[iid])
        await db.flush()


# ═══════════════════════════════════════════════════════════════════════════
# Consumption CRUD
# ═══════════════════════════════════════════════════════════════════════════


async def list_consumptions(
    db: AsyncSession, user_id: uuid.UUID, consumed_date: date | None = None
) -> list[dict]:
    stmt = select(DietConsumption).where(DietConsumption.user_id == user_id)
    if consumed_date:
        stmt = stmt.where(DietConsumption.consumed_date == consumed_date)
    stmt = stmt.order_by(
        DietConsumption.consumed_date.desc(), DietConsumption.created_at
    ).limit(200)
    result = await db.execute(stmt)
    return [consumption_dict(c) for c in result.scalars().all()]


async def create_consumption(db: AsyncSession, user_id: uuid.UUID, **kwargs) -> dict:
    diet_id = kwargs.pop("diet_id", None)
    consumed_date_val = kwargs.pop("consumed_date", None)
    if diet_id is not None:
        diet_result = await db.execute(
            select(Diet).where(Diet.id == diet_id, Diet.user_id == user_id)
        )
        if diet_result.scalar_one_or_none() is None:
            raise ValueError("Diet not found")
    consumption = DietConsumption(
        user_id=user_id,
        consumed_date=consumed_date_val or local_today(),
        **kwargs,
    )
    db.add(consumption)
    await db.flush()
    await db.refresh(consumption)
    return consumption_dict(consumption)


async def delete_consumption(
    db: AsyncSession, user_id: uuid.UUID, consumption_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(DietConsumption).where(
            DietConsumption.id == consumption_id, DietConsumption.user_id == user_id
        )
    )
    consumption = result.scalar_one_or_none()
    if not consumption:
        raise ValueError("Consumption not found")
    await db.delete(consumption)


# ═══════════════════════════════════════════════════════════════════════════
# LLM: generate a diet plan
# ═══════════════════════════════════════════════════════════════════════════


async def execute_diet_generation(
    db: AsyncSession,
    user_id: uuid.UUID,
    locale: str,
    *,
    direction: str | None = None,
    goal: str | None = None,
    preferences: str | None = None,
) -> dict:
    active_config = await get_active_llm_config(db, user_id)
    if active_config is None:
        raise ValueError("No active LLM provider configured")
    safe_direction = direction if direction in DIET_DIRECTIONS else None
    try:
        diet = await generate_diet(
            db=db,
            user_id=user_id,
            llm_config=active_config,
            locale=locale,
            direction=safe_direction,
            goal=goal,
            preferences=preferences,
        )
    except (JsonRepairError, ValueError):
        raise
    await db.refresh(diet)
    return diet_dict(diet)


# ═══════════════════════════════════════════════════════════════════════════
# LLM: evaluate adherence + adjust plan
# ═══════════════════════════════════════════════════════════════════════════


async def execute_diet_evaluation(
    db: AsyncSession,
    user_id: uuid.UUID,
    diet_id: uuid.UUID,
    locale: str,
    *,
    days: int = 7,
) -> dict:
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user_id))
    diet = result.scalar_one_or_none()
    if not diet:
        raise ValueError("Diet not found")
    active_config = await get_active_llm_config(db, user_id)
    if active_config is None:
        raise ValueError("No active LLM provider configured")
    try:
        evaluation = await evaluate_diet(
            db=db, diet=diet, llm_config=active_config, locale=locale, days=days
        )
    except (JsonRepairError, ValueError):
        raise
    await db.refresh(diet)
    return {"evaluation": evaluation, "diet": diet_dict(diet)}


# ═══════════════════════════════════════════════════════════════════════════
# Evaluation history
# ═══════════════════════════════════════════════════════════════════════════


async def list_evaluations(
    db: AsyncSession, user_id: uuid.UUID, diet_id: uuid.UUID
) -> list[dict]:
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user_id))
    if result.scalar_one_or_none() is None:
        raise ValueError("Diet not found")
    ev_result = await db.execute(
        select(DietEvaluation)
        .where(DietEvaluation.diet_id == diet_id)
        .order_by(DietEvaluation.created_at.desc(), DietEvaluation.id.desc())
        .limit(50)
    )
    return [evaluation_dict(ev) for ev in ev_result.scalars().all()]


# ═══════════════════════════════════════════════════════════════════════════
# LLM: diet ↔ training synergy
# ═══════════════════════════════════════════════════════════════════════════


async def execute_synergy_analysis(
    db: AsyncSession,
    user_id: uuid.UUID,
    locale: str,
    *,
    days: int = 7,
) -> dict:
    active_config = await get_active_llm_config(db, user_id)
    if active_config is None:
        raise ValueError("No active LLM provider configured")
    try:
        review = await analyze_diet_training_synergy(
            db=db, user_id=user_id, llm_config=active_config, locale=locale, days=days
        )
    except (JsonRepairError, ValueError):
        raise
    await db.refresh(review)
    return review_dict(review)


async def list_synergy_reviews(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(DietTrainingReview)
        .where(DietTrainingReview.user_id == user_id)
        .order_by(DietTrainingReview.created_at.desc(), DietTrainingReview.id.desc())
        .limit(20)
    )
    return [review_dict(r) for r in result.scalars().all()]
