"""Catalog Service — shared helpers + business logic from app.api.catalog.

Note: catalog_options() is used by pickers in journal/entities/locktimer_ui.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import CATALOG_DOMAINS, ActivityCatalogItem
from app.models.category import ActivityCategory


def validate_domains(raw: str) -> list[str] | None:
    """Parse domain string (comma-separated) into a validated list."""
    if not raw.strip():
        return None
    parts = [d.strip() for d in raw.split(",") if d.strip()]
    valid = [d for d in parts if d in CATALOG_DOMAINS]
    return valid or None


async def catalog_options(
    db: AsyncSession,
    user_id: uuid.UUID,
    domain: str | None = None,
) -> list[dict]:
    """Return [{id, name, owner_id}] of visible catalog items."""
    result = await db.execute(
        select(ActivityCatalogItem)
        .where(or_(ActivityCatalogItem.owner_id.is_(None), ActivityCatalogItem.owner_id == user_id))
        .order_by(ActivityCatalogItem.name.asc())
    )
    items = result.scalars().all()
    out: list[dict] = []
    for it in items:
        if domain and it.domains and domain not in it.domains:
            continue
        out.append({
            "id": str(it.id),
            "name": it.name,
            "owner_id": str(it.owner_id) if it.owner_id else None,
        })
    return out


async def get_catalog_page_context(
    db: AsyncSession, user_id: uuid.UUID, domain: str | None = None,
):
    result = await db.execute(
        select(ActivityCatalogItem)
        .where(or_(ActivityCatalogItem.owner_id.is_(None), ActivityCatalogItem.owner_id == user_id))
        .order_by(ActivityCatalogItem.name.asc())
    )
    items = result.scalars().all()
    categories = (await db.execute(select(ActivityCategory))).scalars().all()
    return {
        "items": items,
        "domains": CATALOG_DOMAINS,
        "selected_domain": domain,
        "categories": categories,
    }


async def create_catalog_item(db: AsyncSession, user_id: uuid.UUID, **kwargs):
    item = ActivityCatalogItem(owner_id=user_id, **kwargs)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def delete_catalog_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID):
    result = await db.execute(
        select(ActivityCatalogItem).where(
            ActivityCatalogItem.id == item_id, ActivityCatalogItem.owner_id == user_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise ValueError("Item not found")
    await db.delete(item)
