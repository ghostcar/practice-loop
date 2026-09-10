"""Personal Care — Dashboard summary and query helpers."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.care import CareEntry, CareEntryProduct, CareRoutine
from app.models.life import InventoryItem
from app.models.media import MediaAsset
from app.timeutils import local_today


async def get_care_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    today = local_today()
    since = today - timedelta(days=30)
    rows = (
        (
            await db.execute(
                select(CareEntry)
                .where(CareEntry.user_id == user_id, CareEntry.entry_date >= since)
                .order_by(CareEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    total = (await db.execute(select(func.count(CareEntry.id)).where(CareEntry.user_id == user_id))).scalar() or 0
    routines = (
        await db.execute(select(func.count(CareRoutine.id)).where(CareRoutine.user_id == user_id))
    ).scalar() or 0
    last = rows[0] if rows else None
    return {
        "count_30d": len(rows),
        "total": total,
        "routines": routines,
        "last_date": last.entry_date.isoformat() if last else None,
        "last_routine": last.routine.name if last and last.routine else None,
    }


async def media_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, list[dict]]:
    rows = (
        (
            await db.execute(
                select(MediaAsset)
                .where(
                    MediaAsset.owner_id == user_id,
                    MediaAsset.owner_type.in_(["care_entry", "care_product"]),
                )
                .order_by(MediaAsset.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, list[dict]] = {}
    for a in rows:
        key = str(a.owner_ref_id) if a.owner_ref_id else ""
        if not key:
            continue
        out.setdefault(key, []).append(
            {
                "id": str(a.id),
                "has_thumbnail": a.thumbnail_path is not None,
                "is_image": (a.mime_type or "").startswith("image/"),
                "caption": a.caption,
            }
        )
    return out


async def entry_product_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, list[str]]:
    rows = (
        await db.execute(
            select(CareEntryProduct.entry_id, CareEntryProduct.product_id)
            .join(CareEntry, CareEntry.id == CareEntryProduct.entry_id)
            .where(CareEntry.user_id == user_id)
        )
    ).all()
    out: dict[str, list[str]] = {}
    for entry_id, product_id in rows:
        out.setdefault(str(entry_id), []).append(str(product_id))
    return out


async def inventory_options(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(InventoryItem)
                .where(
                    InventoryItem.user_id == user_id,
                    InventoryItem.migrated_to_medication.is_(False),
                    InventoryItem.inventory_status != "archived",
                )
                .order_by(InventoryItem.sort_order.asc(), InventoryItem.name.asc())
            )
        )
        .scalars()
        .all()
    )
    return [{"id": str(i.id), "name": i.name, "status": i.inventory_status, "category": i.category} for i in rows]
