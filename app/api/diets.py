"""Diets API: combinable diet plans with food items.

A user may create several diets (each aimed at a different goal), toggle any
subset active at once (combining diets), and reorder items within a diet.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.diet import Diet, DietItem
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(prefix="/diets", tags=["diets"])


# ── Schemas ──


class DietCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool = False


class DietUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None


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
        "goal": d.goal,
        "description": d.description,
        "is_active": d.is_active,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
    if with_items:
        out["items"] = [_item_dict(i) for i in d.items]
    return out


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
    await db.commit()
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
    await db.commit()
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
    await db.commit()
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
    await db.commit()
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
    await db.commit()
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
    await db.commit()
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
