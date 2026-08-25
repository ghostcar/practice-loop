"""Diets API — thin HTTP wrappers over diets_service."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services.diets_service import (
    add_diet_item,
    create_consumption,
    create_diet,
    delete_consumption,
    delete_diet,
    delete_diet_item,
    execute_diet_evaluation,
    execute_diet_generation,
    execute_synergy_analysis,
    get_diets_page_context,
    list_consumptions,
    list_diets,
    list_evaluations,
    list_synergy_reviews,
    reorder_diet_items,
    update_diet,
    update_diet_item,
)
from app.templates_setup import templates

router = APIRouter(prefix="/diets", tags=["diets"])

# ── Pydantic request schemas ──


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
    ctx = await get_diets_page_context(db, user)
    return templates.TemplateResponse(
        request=request,
        name="diets.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "diets",
            **ctx,
        },
    )


# ── Diet CRUD ──


@router.get("/api")
async def list_diets_api(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await list_diets(db, user.id)


@router.post("/api")
async def create_diet_api(
    data: DietCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await create_diet(db, user.id, **data.model_dump())


@router.put("/api/{diet_id}")
async def update_diet_api(
    diet_id: uuid.UUID,
    data: DietUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await update_diet(db, user.id, diet_id, **data.model_dump(exclude_unset=True))
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(404, "Diet not found") from None


@router.delete("/api/{diet_id}")
async def delete_diet_api(
    diet_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await delete_diet(db, user.id, diet_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(404, "Diet not found") from None
    return {"status": "deleted"}


# ── Items ──


@router.post("/api/{diet_id}/items")
async def add_item_api(
    diet_id: uuid.UUID,
    data: DietItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await add_diet_item(db, user.id, diet_id, **data.model_dump())
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(404, "Diet not found") from None


@router.put("/api/{diet_id}/items/{item_id}")
async def update_item_api(
    diet_id: uuid.UUID,
    item_id: uuid.UUID,
    data: DietItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await update_diet_item(db, user.id, item_id, **data.model_dump(exclude_unset=True))
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(404, "Diet item not found") from None


@router.delete("/api/{diet_id}/items/{item_id}")
async def delete_item_api(
    diet_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await delete_diet_item(db, user.id, item_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(404, "Diet item not found") from None
    return {"status": "deleted"}


@router.post("/api/{diet_id}/items/reorder")
async def reorder_items_api(
    diet_id: uuid.UUID,
    payload: ReorderPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await reorder_diet_items(db, user.id, diet_id, payload.ids)
    except ValueError as e:
        from fastapi import HTTPException
        code = 400 if "must match" in str(e) else 404
        raise HTTPException(code, str(e)) from None
    return {"status": "ok"}


# ── Consumptions ──


@router.get("/api/consumptions")
async def list_consumptions_api(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    consumed_date: date | None = None,
):
    return await list_consumptions(db, user.id, consumed_date)


@router.post("/api/consumptions")
async def create_consumption_api(
    data: ConsumptionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await create_consumption(
            db,
            user.id,
            name=data.name,
            quantity=data.quantity,
            unit=data.unit,
            meal_time=data.meal_time,
            diet_id=data.diet_id,
            consumed_date=data.consumed_date,
            notes=data.notes,
        )
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(404, "Diet not found") from None


@router.delete("/api/consumptions/{consumption_id}")
async def delete_consumption_api(
    consumption_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await delete_consumption(db, user.id, consumption_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(404, "Consumption not found") from None
    return {"status": "deleted"}


# ── LLM: generate ──


@router.post("/api/generate")
async def generate_diet_plan_api(
    data: DietGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    try:
        return await execute_diet_generation(
            db, user.id, locale,
            direction=data.direction, goal=data.goal, preferences=data.preferences,
        )
    except ValueError as e:
        from fastapi import HTTPException
        if "LLM provider" in str(e):
            raise HTTPException(400, str(e)) from None
        raise HTTPException(422, str(e)) from None


# ── LLM: evaluate ──


@router.post("/api/{diet_id}/evaluate")
async def evaluate_diet_plan_api(
    diet_id: uuid.UUID,
    data: DietEvaluateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    try:
        return await execute_diet_evaluation(db, user.id, diet_id, locale, days=data.days)
    except ValueError as e:
        from fastapi import HTTPException
        if "Diet not found" in str(e):
            raise HTTPException(404, str(e)) from None
        if "LLM provider" in str(e):
            raise HTTPException(400, str(e)) from None
        raise HTTPException(422, str(e)) from None


# ── Evaluation history ──


@router.get("/api/{diet_id}/evaluations")
async def list_evaluations_api(
    diet_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await list_evaluations(db, user.id, diet_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(404, "Diet not found") from None


# ── LLM: synergy ──


@router.post("/api/synergy")
async def create_synergy_api(
    data: SynergyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    try:
        return await execute_synergy_analysis(db, user.id, locale, days=data.days)
    except ValueError as e:
        from fastapi import HTTPException
        if "LLM provider" in str(e):
            raise HTTPException(400, str(e)) from None
        raise HTTPException(422, str(e)) from None


@router.get("/api/synergy")
async def list_synergy_api(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await list_synergy_reviews(db, user.id)
