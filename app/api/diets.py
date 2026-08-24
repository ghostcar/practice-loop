"""Diets API: combinable diet plans with food items + actual consumption.

A user may create several diets (each aimed at a different direction/goal),
toggle any subset active at once (combining diets), reorder items within a
diet, log what they actually ate (diet_consumptions), and ask the LLM to
generate a diet or evaluate adherence against the plan.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.pipeline import (
    analyze_diet_training_synergy,
    evaluate_diet,
    generate_diet,
    get_active_llm_config,
)
from app.llm.repair import JsonRepairError
from app.models.diet import Diet, DietConsumption, DietEvaluation, DietItem, DietTrainingReview
from app.models.user import User
from app.templates_setup import templates
from app.timeutils import local_today

router = APIRouter(prefix="/diets", tags=["diets"])

# Allowed diet directions (why the diet exists). Free-form goal text is still
# accepted, this list powers the UI selector + LLM generation.
DIET_DIRECTIONS = {"weight_loss", "muscle_gain", "health", "energy", "endurance", "general", "other"}


# ── Schemas ──


class DietCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    direction: str | None = Field(default=None, max_length=50)
    goal: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool = False


class DietUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    direction: str | None = Field(default=None, max_length=50)
    goal: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None


class DietGenerateRequest(BaseModel):
    direction: str | None = Field(default=None, max_length=50)
    goal: str | None = Field(default=None, max_length=500)
    preferences: str | None = Field(default=None, max_length=1000)


class DietEvaluateRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)


class SynergyRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)


class ConsumptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    quantity: float | None = None
    unit: str | None = Field(default=None, max_length=20)
    meal_time: str | None = Field(default=None, max_length=30)
    diet_id: uuid.UUID | None = None
    consumed_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class DietItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    quantity: float | None = None
    unit: str | None = Field(default=None, max_length=20)
    meal_time: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)


class DietItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    quantity: float | None = None
    unit: str | None = Field(default=None, max_length=20)
    meal_time: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)


class ReorderPayload(BaseModel):
    ids: list[uuid.UUID]


# ── Serialization ──


def _item_dict(it: DietItem) -> dict:
    return {
        "id": str(it.id),
        "name": it.name,
        "quantity": it.quantity,
        "unit": it.unit,
        "meal_time": it.meal_time,
        "notes": it.notes,
        "sort_order": it.sort_order,
    }


def _diet_dict(d: Diet, with_items: bool = True) -> dict:
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
        out["items"] = [_item_dict(i) for i in d.items]
    return out


def _consumption_dict(c: DietConsumption) -> dict:
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


def _evaluation_dict(ev: DietEvaluation) -> dict:
    return {
        "id": str(ev.id),
        "score": ev.score,
        "summary": ev.summary,
        "findings": ev.findings or [],
        "applied": ev.applied or [],
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


def _review_dict(r: DietTrainingReview) -> dict:
    return {
        "id": str(r.id),
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "analysis": r.analysis,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ── Page ──


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def diets_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    result = await db.execute(
        select(Diet).where(Diet.user_id == user.id).order_by(Diet.is_active.desc(), Diet.created_at.asc())
    )
    diets = [_diet_dict(d) for d in result.scalars().all()]
    active_config = await get_active_llm_config(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="diets.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "diets": diets,
            "active_config": active_config,
            "directions": sorted(DIET_DIRECTIONS),
            "today": local_today().isoformat(),
            "active_nav": "diets",
        },
    )


# ── Diet CRUD ──


@router.get("/api")
async def list_diets(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all diets with items (for the JS-driven page)."""
    result = await db.execute(
        select(Diet).where(Diet.user_id == user.id).order_by(Diet.is_active.desc(), Diet.created_at.asc())
    )
    return [_diet_dict(d) for d in result.scalars().all()]


@router.post("/api")
async def create_diet(
    data: DietCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    diet = Diet(user_id=user.id, **data.model_dump())
    db.add(diet)
    await db.flush()
    await db.refresh(diet)
    return _diet_dict(diet)


@router.put("/api/{diet_id}")
async def update_diet(
    diet_id: uuid.UUID,
    data: DietUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user.id))
    diet = result.scalar_one_or_none()
    if not diet:
        raise HTTPException(404, "Diet not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(diet, k, v)
    db.add(diet)
    await db.flush()
    await db.refresh(diet)
    return _diet_dict(diet)


@router.delete("/api/{diet_id}")
async def delete_diet(
    diet_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user.id))
    diet = result.scalar_one_or_none()
    if not diet:
        raise HTTPException(404, "Diet not found")
    await db.delete(diet)
    return {"status": "deleted"}


# ── Items ──


@router.post("/api/{diet_id}/items")
async def add_diet_item(
    diet_id: uuid.UUID,
    data: DietItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user.id))
    diet = result.scalar_one_or_none()
    if not diet:
        raise HTTPException(404, "Diet not found")
    max_o = await db.execute(
        select(DietItem.sort_order).where(DietItem.diet_id == diet_id).order_by(DietItem.sort_order.desc()).limit(1)
    )
    next_order = (max_o.scalar_one_or_none() or -1) + 1
    item = DietItem(diet_id=diet_id, sort_order=next_order, **data.model_dump())
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return _item_dict(item)


@router.put("/api/{diet_id}/items/{item_id}")
async def update_diet_item(
    diet_id: uuid.UUID,
    item_id: uuid.UUID,
    data: DietItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(DietItem).join(Diet, Diet.id == DietItem.diet_id).where(DietItem.id == item_id, Diet.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Diet item not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return _item_dict(item)


@router.delete("/api/{diet_id}/items/{item_id}")
async def delete_diet_item(
    diet_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(DietItem).join(Diet, Diet.id == DietItem.diet_id).where(DietItem.id == item_id, Diet.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Diet item not found")
    await db.delete(item)
    return {"status": "deleted"}


@router.post("/api/{diet_id}/items/reorder")
async def reorder_diet_items(
    diet_id: uuid.UUID,
    payload: ReorderPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(DietItem)
        .join(Diet, Diet.id == DietItem.diet_id)
        .where(DietItem.diet_id == diet_id, Diet.user_id == user.id)
    )
    items = {i.id: i for i in result.scalars().all()}
    if set(payload.ids) != set(items.keys()):
        raise HTTPException(400, "ids must match all items of the diet")
    for pos, iid in enumerate(payload.ids):
        items[iid].sort_order = pos
        db.add(items[iid])
        await db.flush()
    return {"status": "ok"}


# ── Actual consumption (the «fact» side) ──


@router.get("/api/consumptions")
async def list_consumptions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    consumed_date: date | None = None,
):
    """List what the user actually ate; filter by date if given."""
    stmt = select(DietConsumption).where(DietConsumption.user_id == user.id)
    if consumed_date:
        stmt = stmt.where(DietConsumption.consumed_date == consumed_date)
    stmt = stmt.order_by(DietConsumption.consumed_date.desc(), DietConsumption.created_at).limit(200)
    result = await db.execute(stmt)
    return [_consumption_dict(c) for c in result.scalars().all()]


@router.post("/api/consumptions")
async def create_consumption(
    data: ConsumptionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Log a food the user actually consumed."""
    if data.diet_id is not None:
        diet_result = await db.execute(select(Diet).where(Diet.id == data.diet_id, Diet.user_id == user.id))
        if diet_result.scalar_one_or_none() is None:
            raise HTTPException(404, "Diet not found")
    consumption = DietConsumption(
        user_id=user.id,
        consumed_date=data.consumed_date or local_today(),
        **data.model_dump(exclude={"consumed_date"}),
    )
    db.add(consumption)
    await db.flush()
    await db.refresh(consumption)
    return _consumption_dict(consumption)


@router.delete("/api/consumptions/{consumption_id}")
async def delete_consumption(
    consumption_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(DietConsumption).where(DietConsumption.id == consumption_id, DietConsumption.user_id == user.id)
    )
    consumption = result.scalar_one_or_none()
    if not consumption:
        raise HTTPException(404, "Consumption not found")
    await db.delete(consumption)
    return {"status": "deleted"}


# ── LLM: generate a diet plan ──


@router.post("/api/generate")
async def generate_diet_plan(
    data: DietGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ask the LLM to create a diet for a given direction/goal/preferences."""
    active_config = await get_active_llm_config(db, user.id)
    if active_config is None:
        raise HTTPException(400, "No active LLM provider configured")
    locale = detect_locale(request, user.locale)
    direction = data.direction if data.direction in DIET_DIRECTIONS else None
    try:
        diet = await generate_diet(
            db=db,
            user_id=user.id,
            llm_config=active_config,
            locale=locale,
            direction=direction,
            goal=data.goal,
            preferences=data.preferences,
        )
    except (JsonRepairError, ValueError) as e:
        raise HTTPException(422, str(e)) from None
    await db.refresh(diet)
    return _diet_dict(diet)


# ── LLM: evaluate adherence + adjust plan ──


@router.post("/api/{diet_id}/evaluate")
async def evaluate_diet_plan(
    diet_id: uuid.UUID,
    data: DietEvaluateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate actual consumption against the plan and apply LLM adjustments."""
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user.id))
    diet = result.scalar_one_or_none()
    if not diet:
        raise HTTPException(404, "Diet not found")
    active_config = await get_active_llm_config(db, user.id)
    if active_config is None:
        raise HTTPException(400, "No active LLM provider configured")
    locale = detect_locale(request, user.locale)
    try:
        evaluation = await evaluate_diet(db=db, diet=diet, llm_config=active_config, locale=locale, days=data.days)
    except (JsonRepairError, ValueError) as e:
        raise HTTPException(422, str(e)) from None
    await db.refresh(diet)
    return {"evaluation": evaluation, "diet": _diet_dict(diet)}


# ── Evaluation history ──


@router.get("/api/{diet_id}/evaluations")
async def list_diet_evaluations(
    diet_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full history of LLM adherence evaluations for one diet (newest first)."""
    result = await db.execute(select(Diet).where(Diet.id == diet_id, Diet.user_id == user.id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Diet not found")
    ev_result = await db.execute(
        select(DietEvaluation)
        .where(DietEvaluation.diet_id == diet_id)
        .order_by(DietEvaluation.created_at.desc(), DietEvaluation.id.desc())
        .limit(50)
    )
    return [_evaluation_dict(ev) for ev in ev_result.scalars().all()]


# ── LLM: diet ↔ training synergy ──


@router.post("/api/synergy")
async def create_synergy_review(
    data: SynergyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run an LLM analysis of how diets and training influence each other."""
    active_config = await get_active_llm_config(db, user.id)
    if active_config is None:
        raise HTTPException(400, "No active LLM provider configured")
    locale = detect_locale(request, user.locale)
    try:
        review = await analyze_diet_training_synergy(
            db=db, user_id=user.id, llm_config=active_config, locale=locale, days=data.days
        )
    except (JsonRepairError, ValueError) as e:
        raise HTTPException(422, str(e)) from None
    await db.refresh(review)
    return _review_dict(review)


@router.get("/api/synergy")
async def list_synergy_reviews(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """History of diet↔training synergy reviews (newest first)."""
    result = await db.execute(
        select(DietTrainingReview)
        .where(DietTrainingReview.user_id == user.id)
        .order_by(DietTrainingReview.created_at.desc(), DietTrainingReview.id.desc())
        .limit(20)
    )
    return [_review_dict(r) for r in result.scalars().all()]
