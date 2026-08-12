"""Inventory categories API — read-only reference (REFACTORING.md step 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.inventory_category import InventoryCategory
from app.models.user import User
from app.schemas.references import InventoryCategoryOut

router = APIRouter(tags=["categories"])


@router.get("/inventory-categories", response_model=list[InventoryCategoryOut])
async def list_inventory_categories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InventoryCategory).where(InventoryCategory.is_active.is_(True)).order_by(InventoryCategory.sort_order)
    )
    return [InventoryCategoryOut.model_validate(c) for c in result.scalars().all()]
