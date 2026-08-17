"""Inventory management — CRUD, reorder, image upload/delete, shopping list."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.life import InventoryItem
from app.models.user import User
from app.schemas.points_v2 import InventoryItemCreate, InventoryItemOut, InventoryItemUpdate
from app.services.uploads import delete_upload, save_image

router = APIRouter(tags=["v2"])


class _ReorderPayload(BaseModel):
    ids: list[uuid.UUID]


@router.post("/inventory/reorder")
async def reorder_inventory(
    payload: _ReorderPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persist drag&drop ordering of inventory items.

    Accepts a *subset* of items (the currently rendered, possibly filtered
    list) and re-ranks only those relative to each other; items not mentioned
    keep their original order. This makes drag&drop work with filters active.
    """
    result = await db.execute(select(InventoryItem).where(InventoryItem.user_id == user.id))
    items = list(result.scalars().all())
    by_id = {i.id: i for i in items}
    unknown = [iid for iid in payload.ids if iid not in by_id]
    if unknown:
        raise HTTPException(400, "Unknown item ids in payload")

    # Anchor: the smallest sort_order among the moved items determines where
    # the re-ranked block starts, so unmentioned items stay in place.
    moved = [by_id[iid] for iid in payload.ids]
    anchor = min((i.sort_order for i in moved), default=0)
    for pos, iid in enumerate(payload.ids):
        by_id[iid].sort_order = anchor + pos
        db.add(by_id[iid])

    # Re-normalize all items to dense ranks in the new relative order.
    ordered = sorted(items, key=lambda i: (i.sort_order, i.created_at))
    for pos, i in enumerate(ordered):
        i.sort_order = pos
        db.add(i)
    await db.flush()
    return {"status": "ok"}


@router.post("/inventory/{item_id}/image")
async def upload_inventory_image(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload (or replace) a photo for an inventory item."""
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    url = await save_image(file, subdir="inventory")
    old = item.image_path
    item.image_path = url
    db.add(item)
    await db.commit()
    if old:
        delete_upload(old)
    return {"status": "ok", "image_path": url}


@router.delete("/inventory/{item_id}/image")
async def delete_inventory_image(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove the photo from an inventory item."""
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    old = item.image_path
    item.image_path = None
    db.add(item)
    await db.commit()
    if old:
        delete_upload(old)
    return {"status": "ok"}


@router.get("/inventory", response_model=list[InventoryItemOut])
async def get_inventory(
    category: str | None = None,
    status: str | None = None,
    shopping_list: bool | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(InventoryItem).where(
        InventoryItem.user_id == user.id, InventoryItem.migrated_to_medication.is_(False)
    )
    if category:
        query = query.where(InventoryItem.category == category)
    if status:
        query = query.where(InventoryItem.status == status)
    if shopping_list is not None:
        query = query.where(InventoryItem.is_shopping_list == shopping_list)
    query = query.order_by(InventoryItem.sort_order.asc(), InventoryItem.priority.desc(), InventoryItem.name)
    result = await db.execute(query)
    return [InventoryItemOut.model_validate(i) for i in result.scalars().all()]


@router.get("/inventory/shopping-list", response_model=list[InventoryItemOut])
async def get_shopping_list(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InventoryItem)
        .where(
            InventoryItem.user_id == user.id,
            InventoryItem.is_shopping_list.is_(True),
            InventoryItem.migrated_to_medication.is_(False),
        )
        .order_by(InventoryItem.priority.desc())
    )
    return [InventoryItemOut.model_validate(i) for i in result.scalars().all()]


@router.post("/inventory", response_model=InventoryItemOut)
async def create_inventory_item(
    data: InventoryItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = InventoryItem(user_id=user.id, **data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return InventoryItemOut.model_validate(item)


@router.put("/inventory/{item_id}", response_model=InventoryItemOut)
async def update_inventory_item(
    item_id: uuid.UUID,
    data: InventoryItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return InventoryItemOut.model_validate(item)


@router.delete("/inventory/{item_id}")
async def delete_inventory_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    await db.delete(item)
    await db.commit()
    return {"status": "deleted"}
