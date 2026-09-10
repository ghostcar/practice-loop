"""Personal Care — Helpers, parsers, validators, resolvers."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.care import SCALE_1_5, CareProduct, CareRoutine
from app.models.catalog import ActivityCatalogItem
from app.models.life import InventoryItem
from app.services.errors import NotFoundError


def _now_utc() -> datetime:
    return datetime.now(UTC)


def parse_int(raw: str, field_name: str, minimum: int = 0, maximum: int = 10000) -> int | None:
    if not raw.strip():
        return None
    try:
        v = int(raw)
    except ValueError:
        raise ValueError(f"Invalid {field_name}") from None
    if v < minimum or v > maximum:
        raise ValueError(f"Invalid {field_name} (out of range)")
    return v


def parse_date(raw: str, field_name: str) -> date | None:
    if not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise ValueError(f"Invalid {field_name} (ISO 8601)") from None


def parse_scale(raw: str, field_name: str) -> int:
    try:
        v = int(raw)
    except ValueError:
        raise ValueError(f"Invalid {field_name} (1-5)") from None
    if v not in SCALE_1_5:
        raise ValueError(f"Invalid {field_name} (1-5)")
    return v


async def validate_routine(db: AsyncSession, routine_id: str, user_id: uuid.UUID) -> uuid.UUID | None:
    if not routine_id.strip():
        return None
    try:
        rid = uuid.UUID(routine_id.strip())
    except ValueError:
        raise ValueError("Invalid routine_id") from None
    routine = (
        await db.execute(select(CareRoutine).where(CareRoutine.id == rid, CareRoutine.user_id == user_id))
    ).scalar_one_or_none()
    if routine is None:
        raise NotFoundError("Routine not found")
    return rid


async def resolve_catalog_item(
    db: AsyncSession, catalog_item_id: str | uuid.UUID | None, user_id: uuid.UUID
) -> ActivityCatalogItem | None:
    if not catalog_item_id:
        return None
    try:
        cid = uuid.UUID(str(catalog_item_id))
    except ValueError:
        raise ValueError("Invalid catalog_item_id") from None
    item = (
        await db.execute(
            select(ActivityCatalogItem).where(
                ActivityCatalogItem.id == cid,
                ActivityCatalogItem.owner_id.is_(None) | (ActivityCatalogItem.owner_id == user_id),
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Catalog item not found")
    return item


async def resolve_inventory_item(
    db: AsyncSession, inventory_item_id: str | uuid.UUID | None, user_id: uuid.UUID
) -> InventoryItem | None:
    if not inventory_item_id:
        return None
    try:
        iid = uuid.UUID(str(inventory_item_id))
    except ValueError:
        raise ValueError("Invalid inventory_item_id") from None
    item = (
        await db.execute(select(InventoryItem).where(InventoryItem.id == iid, InventoryItem.user_id == user_id))
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Inventory item not found")
    return item


async def resolve_products(
    db: AsyncSession, product_ids: list[str | uuid.UUID] | None, user_id: uuid.UUID
) -> list[uuid.UUID]:
    if not product_ids:
        return []
    out: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for raw in product_ids:
        if not raw:
            continue
        try:
            pid = uuid.UUID(str(raw))
        except ValueError:
            raise ValueError("Invalid product_id") from None
        if pid in seen:
            continue
        product = (
            await db.execute(select(CareProduct).where(CareProduct.id == pid, CareProduct.user_id == user_id))
        ).scalar_one_or_none()
        if product is None:
            raise NotFoundError("Product not found")
        seen.add(pid)
        out.append(pid)
    return out
