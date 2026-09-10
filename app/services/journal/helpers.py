"""Sexual Journal — Helpers, validators, resolvers."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import SCALE_1_5, JournalPartner
from app.services.errors import NotFoundError


def parse_scale(raw: str, field_name: str) -> int | None:
    if not raw.strip():
        return None
    try:
        v = int(raw)
    except ValueError:
        raise ValueError(f"Invalid {field_name} (1-5)") from None
    if v not in SCALE_1_5:
        raise ValueError(f"Invalid {field_name} (1-5)")
    return v


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


def validate_partner_id(partner_id: str) -> uuid.UUID | None:
    if not partner_id.strip():
        return None
    try:
        return uuid.UUID(partner_id.strip())
    except ValueError:
        raise ValueError("Invalid partner_id") from None


async def validate_activity_log(
    db: AsyncSession, activity_log_id: str | uuid.UUID | None, user_id: uuid.UUID
) -> uuid.UUID | None:
    from app.models.activity_log import ActivityLog

    if not activity_log_id:
        return None
    try:
        aid = uuid.UUID(str(activity_log_id))
    except ValueError:
        raise ValueError("Invalid activity_log_id") from None
    task = (
        await db.execute(select(ActivityLog).where(ActivityLog.id == aid, ActivityLog.user_id == user_id))
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError("Activity not found")
    return aid


async def validate_care_products(
    db: AsyncSession, care_product_ids: str | list[uuid.UUID] | None, user_id: uuid.UUID
) -> list[str] | None:
    if care_product_ids is None:
        return None
    if isinstance(care_product_ids, str):
        raw = [x.strip() for x in care_product_ids.split(",") if x.strip()]
        if not raw:
            return None
        try:
            parsed = [uuid.UUID(x) for x in raw]
        except ValueError:
            raise ValueError("Invalid care_product_ids") from None
    else:
        parsed = list(care_product_ids)
    if not parsed:
        return None
    from app.models.care import CareProduct

    rows = (
        (await db.execute(select(CareProduct.id).where(CareProduct.id.in_(parsed), CareProduct.user_id == user_id)))
        .scalars()
        .all()
    )
    if len(rows) != len(set(parsed)):
        raise ValueError("One or more care products not found")
    return [str(x) for x in parsed]


async def resolve_catalog_item(db: AsyncSession, catalog_item_id: str | uuid.UUID | None, user_id: uuid.UUID):
    from app.models.catalog import ActivityCatalogItem

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


async def validate_partner(db: AsyncSession, partner_id: str, user_id: uuid.UUID) -> uuid.UUID | None:
    pid = validate_partner_id(partner_id)
    if pid is None:
        return None
    partner = (
        await db.execute(select(JournalPartner).where(JournalPartner.id == pid, JournalPartner.user_id == user_id))
    ).scalar_one_or_none()
    if partner is None:
        raise NotFoundError("Partner not found")
    return pid
