"""Personal Care — Business Logic Service Layer.

Extracted from app/api/care.py (ADR-161) to keep routers thin:
all CRUD, validation, serialization, and domain queries live here.

Public API:
  - get_care_page_context(db, user) → dict  (template context for /care)
  - get_care_summary(db, user_id) → dict    (dashboard summary)
  - create_routine / delete_routine
  - create_product / delete_product
  - create_entry / delete_entry
  - attach_entry_media / attach_product_media
  - create_course / delete_course / mark_course_session_done / mark_course_session_skipped
  - json_care_summary / json_list_products / json_list_courses
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.care import (
    CARE_AREAS,
    CARE_KINDS,
    CARE_PRODUCT_CATEGORIES,
    SCALE_1_5,
    CareCourse,
    CareCourseSession,
    CareEntry,
    CareEntryProduct,
    CareProduct,
    CareRoutine,
    CareRoutineProduct,
)
from app.models.catalog import ActivityCatalogItem
from app.models.life import InventoryItem
from app.models.media import MediaAsset
from app.models.user import User
from app.services.errors import NotFoundError
from app.timeutils import local_today

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Bodies (used by JSON API)
# ─────────────────────────────────────────────────────────────────────────────


class RoutineBody(BaseModel):
    name: str
    catalog_item_id: uuid.UUID | None = None
    area: str = "other"
    kind: str = "home"
    place_name: str | None = Field(default=None, max_length=200)
    place_address: str | None = Field(default=None, max_length=300)
    frequency_days: int | None = Field(default=None, ge=1, le=3650)
    notes: str | None = None
    product_ids: list[uuid.UUID] = Field(default_factory=list)


class EntryBody(BaseModel):
    entry_date: date
    routine_id: uuid.UUID | None = None
    place_name: str | None = Field(default=None, max_length=200)
    place_address: str | None = Field(default=None, max_length=300)
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    skin_reaction: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    product_ids: list[uuid.UUID] = Field(default_factory=list)


class ProductBody(BaseModel):
    name: str
    category: str = "other"
    brand: str | None = None
    notes: str | None = None
    inventory_item_id: uuid.UUID | None = None
    catalog_item_id: uuid.UUID | None = None
    quantity: int = Field(default=0, ge=0, le=100000)
    expiry_date: date | None = None


class CourseBody(BaseModel):
    name: str
    area: str = "other"
    place_name: str | None = Field(default=None, max_length=200)
    place_address: str | None = Field(default=None, max_length=300)
    total_sessions: int = Field(default=1, ge=1, le=200)
    interval_days: int | None = Field(default=None, ge=1, le=3650)
    start_date: date | None = None
    notes: str | None = None
    catalog_item_id: uuid.UUID | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — parsers & validators
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Validators / Resolvers
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Join-table mutations
# ─────────────────────────────────────────────────────────────────────────────


async def set_entry_products(db: AsyncSession, entry_id: uuid.UUID, product_ids: list[uuid.UUID]) -> None:
    await db.execute(delete(CareEntryProduct).where(CareEntryProduct.entry_id == entry_id))
    for pid in product_ids:
        db.add(CareEntryProduct(entry_id=entry_id, product_id=pid))


async def set_routine_products(db: AsyncSession, routine_id: uuid.UUID, product_ids: list[uuid.UUID]) -> None:
    await db.execute(delete(CareRoutineProduct).where(CareRoutineProduct.routine_id == routine_id))
    for pid in product_ids:
        db.add(CareRoutineProduct(routine_id=routine_id, product_id=pid))


# ─────────────────────────────────────────────────────────────────────────────
# Cycle phase snapshot (Personal Care ↔ Cycle, §9.4/§16)
# ─────────────────────────────────────────────────────────────────────────────


async def cycle_snapshot(db: AsyncSession, user_id: uuid.UUID, entry_date: date) -> tuple[str | None, int | None]:
    try:
        from app.api.health import _cycle_phase, _day_of_cycle
        from app.models.health import CycleEvent, CycleSettings
    except Exception:
        return None, None
    settings_row = (
        await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))
    ).scalar_one_or_none()
    events = (await db.execute(select(CycleEvent).where(CycleEvent.user_id == user_id))).scalars().all()
    day = _day_of_cycle(list(events), settings_row, entry_date)
    if day is None:
        return None, None
    phase = _cycle_phase(
        day,
        settings_row.cycle_length if settings_row else 28,
        settings_row.period_length if settings_row else 5,
    )
    return phase, day


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard summary (relief-only, informational)
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers for page / JSON
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Serializers (views)
# ─────────────────────────────────────────────────────────────────────────────


def product_view(
    p: CareProduct,
    usage_by_product: dict[str, int],
    inventory_names: dict[str, dict],
    catalog_names: dict[str, str] | None = None,
) -> dict:
    inv = inventory_names.get(str(p.inventory_item_id)) if p.inventory_item_id else None
    today = local_today()
    low_stock = p.quantity is not None and 0 < p.quantity <= 1
    expiring = p.expiry_date is not None and p.expiry_date <= today + timedelta(days=30)
    return {
        "id": str(p.id),
        "name": p.name,
        "category": p.category,
        "brand": p.brand,
        "notes": p.notes,
        "quantity": p.quantity,
        "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
        "low_stock": low_stock,
        "expiring": expiring,
        "inventory_item_id": str(p.inventory_item_id) if p.inventory_item_id else None,
        "inventory_name": inv["name"] if inv else None,
        "inventory_status": inv["status"] if inv else None,
        "catalog_item_id": str(p.catalog_item_id) if p.catalog_item_id else None,
        "catalog_name": (catalog_names or {}).get(str(p.catalog_item_id)) if p.catalog_item_id else None,
        "usage_count": usage_by_product.get(str(p.id), 0),
    }


def entry_view(
    e: CareEntry,
    routine_names: dict[str, str],
    product_ids_by_entry: dict[str, list[str]] | None = None,
) -> dict:
    product_ids = (product_ids_by_entry or {}).get(str(e.id), [])
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "routine_id": str(e.routine_id) if e.routine_id else None,
        "routine_name": routine_names.get(str(e.routine_id)) if e.routine_id else None,
        "place_name": e.place_name,
        "place_address": e.place_address,
        "duration_minutes": e.duration_minutes,
        "skin_reaction": e.skin_reaction,
        "notes": e.notes,
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
        "product_ids": product_ids,
    }


def routine_json(r: CareRoutine) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "catalog_item_id": str(r.catalog_item_id) if r.catalog_item_id else None,
        "area": r.area,
        "kind": r.kind,
        "place_name": r.place_name,
        "place_address": r.place_address,
        "frequency_days": r.frequency_days,
        "notes": r.notes,
        "product_ids": [str(pr.id) for pr in r.products],
    }


def product_json(p: CareProduct) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "category": p.category,
        "brand": p.brand,
        "notes": p.notes,
        "quantity": p.quantity,
        "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
        "inventory_item_id": str(p.inventory_item_id) if p.inventory_item_id else None,
        "catalog_item_id": str(p.catalog_item_id) if p.catalog_item_id else None,
    }


def entry_json(e: CareEntry, product_ids_by_entry: dict[str, list[str]] | None = None) -> dict:
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "routine_id": str(e.routine_id) if e.routine_id else None,
        "place_name": e.place_name,
        "place_address": e.place_address,
        "duration_minutes": e.duration_minutes,
        "skin_reaction": e.skin_reaction,
        "notes": e.notes,
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
        "product_ids": (product_ids_by_entry or {}).get(str(e.id), []),
    }


def course_json(c: CareCourse) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "catalog_item_id": str(c.catalog_item_id) if c.catalog_item_id else None,
        "area": c.area,
        "place_name": c.place_name,
        "place_address": c.place_address,
        "total_sessions": c.total_sessions,
        "interval_days": c.interval_days,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "notes": c.notes,
        "status": c.status,
        "sessions": [
            {
                "id": str(s.id),
                "session_number": s.session_number,
                "scheduled_date": s.scheduled_date.isoformat(),
                "status": s.status,
                "entry_id": str(s.entry_id) if s.entry_id else None,
                "notes": s.notes,
            }
            for s in sorted(c.sessions, key=lambda s: s.session_number)
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page context builder
# ─────────────────────────────────────────────────────────────────────────────


async def get_care_page_context(db: AsyncSession, user: User) -> dict:
    """Build full template context for GET /care page."""
    from app.api.catalog import catalog_options

    today = local_today()
    routines = (
        (await db.execute(select(CareRoutine).where(CareRoutine.user_id == user.id).order_by(CareRoutine.name.asc())))
        .scalars()
        .all()
    )
    routine_names = {str(r.id): r.name for r in routines}
    entries = (
        (await db.execute(select(CareEntry).where(CareEntry.user_id == user.id).order_by(CareEntry.entry_date.desc())))
        .scalars()
        .all()
    )
    media = await media_map(db, user.id)
    catalog_items = await catalog_options(db, user.id, domain="care")
    products = (
        (await db.execute(select(CareProduct).where(CareProduct.user_id == user.id).order_by(CareProduct.name.asc())))
        .scalars()
        .all()
    )
    product_usage = (
        await db.execute(
            select(CareEntryProduct.product_id, func.count(CareEntryProduct.id))
            .join(CareEntry, CareEntry.id == CareEntryProduct.entry_id)
            .where(CareEntry.user_id == user.id)
            .group_by(CareEntryProduct.product_id)
        )
    ).all()
    usage_by_product = {str(pid): cnt for pid, cnt in product_usage}
    inv_options = await inventory_options(db, user.id)
    inventory_names = {i["id"]: i for i in inv_options}
    catalog_names = {c["id"]: c["name"] for c in catalog_items}
    product_names = {str(p.id): p.name for p in products}
    prod_map = await entry_product_map(db, user.id)

    courses = (
        (
            await db.execute(
                select(CareCourse).where(CareCourse.user_id == user.id).order_by(CareCourse.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    course_views = [
        {
            "id": str(c.id),
            "name": c.name,
            "area": c.area,
            "place_name": c.place_name,
            "place_address": c.place_address,
            "total_sessions": c.total_sessions,
            "interval_days": c.interval_days,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "notes": c.notes,
            "status": c.status,
            "done": sum(1 for s in c.sessions if s.status == "done"),
            "next_date": next(
                (
                    s.scheduled_date.isoformat()
                    for s in sorted(c.sessions, key=lambda s: s.scheduled_date)
                    if s.status == "pending"
                ),
                None,
            ),
            "sessions": [
                {
                    "id": str(s.id),
                    "session_number": s.session_number,
                    "scheduled_date": s.scheduled_date.isoformat(),
                    "status": s.status,
                    "notes": s.notes,
                }
                for s in sorted(c.sessions, key=lambda s: s.session_number)
            ],
        }
        for c in courses
    ]

    return {
        "today": today,
        "courses": course_views,
        "routines": [
            {
                "id": str(r.id),
                "name": r.name,
                "area": r.area,
                "kind": r.kind,
                "place_name": r.place_name,
                "place_address": r.place_address,
                "frequency_days": r.frequency_days,
                "notes": r.notes,
                "entries_count": sum(1 for e in entries if e.routine_id == r.id),
                "product_ids": [str(pr.id) for pr in r.products],
            }
            for r in routines
        ],
        "entries": [entry_view(e, routine_names, prod_map) for e in entries],
        "media": media,
        "catalog_items": catalog_items,
        "products": [product_view(p, usage_by_product, inventory_names, catalog_names) for p in products],
        "product_names": product_names,
        "inventory_options": inv_options,
        "care_areas": list(CARE_AREAS),
        "care_kinds": list(CARE_KINDS),
        "care_product_categories": list(CARE_PRODUCT_CATEGORIES),
        "scales": list(SCALE_1_5),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Routines
# ─────────────────────────────────────────────────────────────────────────────


async def create_routine(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    area: str,
    kind: str,
    place_name: str,
    place_address: str,
    frequency_days: str,
    notes: str,
    catalog_item_id: str,
    product_ids: list[str],
) -> CareRoutine:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    area = area if area in CARE_AREAS else "other"
    kind = kind if kind in CARE_KINDS else "home"
    cat_item = await resolve_catalog_item(db, catalog_item_id, user_id)
    resolved = await resolve_products(db, product_ids, user_id)
    freq = None
    if frequency_days.strip():
        freq = parse_int(frequency_days, "frequency_days", minimum=1, maximum=3650)
    routine = CareRoutine(
        user_id=user_id,
        name=name,
        catalog_item_id=cat_item.id if cat_item else None,
        area=area,
        kind=kind,
        place_name=(place_name or "").strip()[:200] or None,
        place_address=(place_address or "").strip()[:300] or None,
        frequency_days=freq,
        notes=(notes or "").strip() or None,
    )
    db.add(routine)
    await db.flush()
    await set_routine_products(db, routine.id, resolved)
    await db.flush()
    return routine


async def delete_routine(db: AsyncSession, user_id: uuid.UUID, routine_id: uuid.UUID) -> None:
    routine = (
        await db.execute(select(CareRoutine).where(CareRoutine.id == routine_id, CareRoutine.user_id == user_id))
    ).scalar_one_or_none()
    if routine is None:
        raise NotFoundError("Routine not found")
    entries = (
        (await db.execute(select(CareEntry).where(CareEntry.user_id == user_id, CareEntry.routine_id == routine_id)))
        .scalars()
        .all()
    )
    for e in entries:
        e.routine_id = None
    await db.execute(delete(CareRoutineProduct).where(CareRoutineProduct.routine_id == routine_id))
    await db.delete(routine)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Products
# ─────────────────────────────────────────────────────────────────────────────


async def create_product(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    category: str,
    brand: str,
    notes: str,
    inventory_item_id: str,
    catalog_item_id: str,
    quantity: str,
    expiry_date: str,
) -> CareProduct:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    category = category if category in CARE_PRODUCT_CATEGORIES else "other"
    inv_item = await resolve_inventory_item(db, inventory_item_id, user_id)
    cat_item = await resolve_catalog_item(db, catalog_item_id, user_id)
    qty = parse_int(quantity, "quantity", minimum=0, maximum=100000) or 0
    exp = parse_date(expiry_date, "expiry_date")
    product = CareProduct(
        user_id=user_id,
        name=name,
        category=category,
        brand=(brand or "").strip()[:120] or None,
        notes=(notes or "").strip() or None,
        inventory_item_id=inv_item.id if inv_item else None,
        catalog_item_id=cat_item.id if cat_item else None,
        quantity=qty,
        expiry_date=exp,
    )
    db.add(product)
    await db.flush()
    return product


async def delete_product(db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID) -> None:
    product = (
        await db.execute(select(CareProduct).where(CareProduct.id == product_id, CareProduct.user_id == user_id))
    ).scalar_one_or_none()
    if product is None:
        raise NotFoundError("Product not found")
    await db.execute(delete(CareEntryProduct).where(CareEntryProduct.product_id == product_id))
    await db.execute(delete(CareRoutineProduct).where(CareRoutineProduct.product_id == product_id))
    await db.delete(product)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Entries
# ─────────────────────────────────────────────────────────────────────────────


async def create_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entry_date: str,
    routine_id: str,
    place_name: str,
    place_address: str,
    duration_minutes: str,
    skin_reaction: str,
    notes: str,
    product_ids: list[str],
) -> CareEntry:
    try:
        d = date.fromisoformat(entry_date.strip())
    except ValueError:
        raise ValueError("Invalid entry_date (ISO 8601)") from None
    rid = await validate_routine(db, routine_id, user_id)
    reaction = parse_scale(skin_reaction, "skin_reaction") if skin_reaction.strip() else None
    resolved = await resolve_products(db, product_ids, user_id)
    cycle_phase, cycle_day = await cycle_snapshot(db, user_id, d)
    entry = CareEntry(
        user_id=user_id,
        routine_id=rid,
        entry_date=d,
        place_name=(place_name or "").strip()[:200] or None,
        place_address=(place_address or "").strip()[:300] or None,
        duration_minutes=parse_int(duration_minutes, "duration_minutes"),
        skin_reaction=reaction,
        notes=(notes or "").strip() or None,
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    db.add(entry)
    await db.flush()
    await set_entry_products(db, entry.id, resolved)
    await db.flush()
    return entry


async def delete_entry(db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    entry = (
        await db.execute(select(CareEntry).where(CareEntry.id == entry_id, CareEntry.user_id == user_id))
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Care entry not found")
    await db.delete(entry)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Media
# ─────────────────────────────────────────────────────────────────────────────


async def attach_entry_media(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entry_id: uuid.UUID,
    file_info: dict,
    caption: str,
) -> MediaAsset:
    entry = (
        await db.execute(select(CareEntry).where(CareEntry.id == entry_id, CareEntry.user_id == user_id))
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Care entry not found")
    asset = MediaAsset(
        owner_id=user_id,
        owner_type="care_entry",
        owner_ref_id=entry.id,
        state="ready",
        file_path=file_info["file_path"],
        thumbnail_path=file_info["thumbnail_path"],
        original_filename=file_info["original_filename"],
        mime_type=file_info["mime_type"],
        file_size_bytes=file_info["file_size_bytes"],
        sha256_hex=file_info["sha256_hex"],
        width=file_info["width"],
        height=file_info["height"],
        caption=(caption or "").strip()[:500] or None,
    )
    db.add(asset)
    await db.flush()
    return asset


async def attach_product_media(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    product_id: uuid.UUID,
    file_info: dict,
    caption: str,
) -> MediaAsset:
    product = (
        await db.execute(select(CareProduct).where(CareProduct.id == product_id, CareProduct.user_id == user_id))
    ).scalar_one_or_none()
    if product is None:
        raise NotFoundError("Care product not found")
    asset = MediaAsset(
        owner_id=user_id,
        owner_type="care_product",
        owner_ref_id=product.id,
        state="ready",
        file_path=file_info["file_path"],
        thumbnail_path=file_info["thumbnail_path"],
        original_filename=file_info["original_filename"],
        mime_type=file_info["mime_type"],
        file_size_bytes=file_info["file_size_bytes"],
        sha256_hex=file_info["sha256_hex"],
        width=file_info["width"],
        height=file_info["height"],
        caption=(caption or "").strip()[:500] or None,
    )
    db.add(asset)
    await db.flush()
    return asset


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Courses
# ─────────────────────────────────────────────────────────────────────────────


async def create_course(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    area: str,
    place_name: str,
    place_address: str,
    total_sessions: str,
    interval_days: str,
    start_date: str,
    notes: str,
    catalog_item_id: str,
) -> CareCourse:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    area = area if area in CARE_AREAS else "other"
    total = parse_int(total_sessions, "total_sessions", minimum=1, maximum=200) or 1
    interval = parse_int(interval_days, "interval_days", minimum=1, maximum=3650)
    start = None
    if start_date.strip():
        try:
            start = date.fromisoformat(start_date.strip())
        except ValueError:
            raise ValueError("Invalid start_date (ISO 8601)") from None
    if start is None:
        start = local_today()
    cat_item = await resolve_catalog_item(db, catalog_item_id, user_id)
    course = CareCourse(
        user_id=user_id,
        name=name,
        catalog_item_id=cat_item.id if cat_item else None,
        area=area,
        place_name=(place_name or "").strip()[:200] or None,
        place_address=(place_address or "").strip()[:300] or None,
        total_sessions=total,
        interval_days=interval,
        start_date=start,
        notes=(notes or "").strip() or None,
        status="active",
    )
    db.add(course)
    await db.flush()
    for i in range(1, total + 1):
        db.add(
            CareCourseSession(
                course_id=course.id,
                session_number=i,
                scheduled_date=start + timedelta(days=(i - 1) * (interval or 0)),
                status="pending",
            )
        )
    await db.flush()
    return course


async def delete_course(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID) -> None:
    course = (
        await db.execute(select(CareCourse).where(CareCourse.id == course_id, CareCourse.user_id == user_id))
    ).scalar_one_or_none()
    if course is None:
        raise NotFoundError("Course not found")
    await db.delete(course)
    await db.flush()


async def _owned_course_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID):
    session = (
        await db.execute(
            select(CareCourseSession)
            .join(CareCourse, CareCourse.id == CareCourseSession.course_id)
            .where(CareCourseSession.id == session_id, CareCourse.user_id == user_id)
        )
    ).scalar_one_or_none()
    if session is None:
        raise NotFoundError("Course session not found")
    return session


async def mark_course_session_done(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID):
    session = await _owned_course_session(db, user_id, session_id)
    session.status = "done"
    session.completed_at = _now_utc()
    await db.flush()
    return session


async def mark_course_session_skipped(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID):
    session = await _owned_course_session(db, user_id, session_id)
    session.status = "skipped"
    session.completed_at = None
    await db.flush()
    return session


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — summaries
# ─────────────────────────────────────────────────────────────────────────────


async def json_care_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    routines = (
        (await db.execute(select(CareRoutine).where(CareRoutine.user_id == user_id).order_by(CareRoutine.name.asc())))
        .scalars()
        .all()
    )
    entries = (
        (await db.execute(select(CareEntry).where(CareEntry.user_id == user_id).order_by(CareEntry.entry_date.desc())))
        .scalars()
        .all()
    )
    products = (
        (await db.execute(select(CareProduct).where(CareProduct.user_id == user_id).order_by(CareProduct.name.asc())))
        .scalars()
        .all()
    )
    prod_map = await entry_product_map(db, user_id)
    return {
        "total_entries": len(entries),
        "routines": [routine_json(r) for r in routines],
        "entries": [entry_json(e, prod_map) for e in entries[:50]],
        "products": [product_json(p) for p in products],
    }


async def json_list_products(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    products = (
        (
            await db.execute(
                select(CareProduct).where(CareProduct.user_id == user_id).order_by(CareProduct.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [product_json(p) for p in products]


async def json_list_courses(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    courses = (
        (
            await db.execute(
                select(CareCourse).where(CareCourse.user_id == user_id).order_by(CareCourse.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [course_json(c) for c in courses]


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — CRUD (Pydantic body variants)
# ─────────────────────────────────────────────────────────────────────────────


async def json_create_routine(db: AsyncSession, user_id: uuid.UUID, body: RoutineBody) -> CareRoutine:
    name = body.name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    area = body.area if body.area in CARE_AREAS else "other"
    kind = body.kind if body.kind in CARE_KINDS else "home"
    cat_item = await resolve_catalog_item(db, body.catalog_item_id, user_id)
    resolved = await resolve_products(db, body.product_ids, user_id)
    routine = CareRoutine(
        user_id=user_id,
        name=name,
        catalog_item_id=cat_item.id if cat_item else None,
        area=area,
        kind=kind,
        place_name=(body.place_name or "").strip()[:200] or None,
        place_address=(body.place_address or "").strip()[:300] or None,
        frequency_days=body.frequency_days,
        notes=(body.notes or "").strip() or None,
    )
    db.add(routine)
    await db.flush()
    await set_routine_products(db, routine.id, resolved)
    await db.flush()
    await db.refresh(routine, ["products"])
    return routine


async def json_create_entry(db: AsyncSession, user_id: uuid.UUID, body: EntryBody) -> tuple[CareEntry, list[uuid.UUID]]:
    rid = None
    if body.routine_id is not None:
        routine = (
            await db.execute(
                select(CareRoutine).where(CareRoutine.id == body.routine_id, CareRoutine.user_id == user_id)
            )
        ).scalar_one_or_none()
        if routine is None:
            raise NotFoundError("Routine not found")
        rid = body.routine_id
    resolved = await resolve_products(db, body.product_ids, user_id)
    cycle_phase, cycle_day = await cycle_snapshot(db, user_id, body.entry_date)
    entry = CareEntry(
        user_id=user_id,
        routine_id=rid,
        entry_date=body.entry_date,
        place_name=(body.place_name or "").strip()[:200] or None,
        place_address=(body.place_address or "").strip()[:300] or None,
        duration_minutes=body.duration_minutes,
        skin_reaction=body.skin_reaction,
        notes=(body.notes or "").strip() or None,
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    db.add(entry)
    await db.flush()
    await set_entry_products(db, entry.id, resolved)
    await db.flush()
    return entry, resolved


async def json_delete_routine(db: AsyncSession, user_id: uuid.UUID, routine_id: uuid.UUID) -> None:
    await delete_routine(db, user_id, routine_id)


async def json_delete_entry(db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    entry = (
        await db.execute(select(CareEntry).where(CareEntry.id == entry_id, CareEntry.user_id == user_id))
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Care entry not found")
    await db.execute(delete(CareEntryProduct).where(CareEntryProduct.entry_id == entry_id))
    await db.delete(entry)
    await db.flush()


async def json_create_product(db: AsyncSession, user_id: uuid.UUID, body: ProductBody) -> CareProduct:
    name = body.name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    category = body.category if body.category in CARE_PRODUCT_CATEGORIES else "other"
    inv_item = await resolve_inventory_item(db, body.inventory_item_id, user_id)
    cat_item = await resolve_catalog_item(db, body.catalog_item_id, user_id)
    product = CareProduct(
        user_id=user_id,
        name=name,
        category=category,
        brand=(body.brand or "").strip()[:120] or None,
        notes=(body.notes or "").strip() or None,
        inventory_item_id=inv_item.id if inv_item else None,
        catalog_item_id=cat_item.id if cat_item else None,
        quantity=body.quantity,
        expiry_date=body.expiry_date,
    )
    db.add(product)
    await db.flush()
    return product


async def json_delete_product(db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID) -> None:
    await delete_product(db, user_id, product_id)


async def json_create_course(db: AsyncSession, user_id: uuid.UUID, body: CourseBody) -> CareCourse:
    name = body.name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    area = body.area if body.area in CARE_AREAS else "other"
    start = body.start_date or local_today()
    cat_item = await resolve_catalog_item(db, body.catalog_item_id, user_id)
    course = CareCourse(
        user_id=user_id,
        name=name,
        catalog_item_id=cat_item.id if cat_item else None,
        area=area,
        place_name=(body.place_name or "").strip()[:200] or None,
        place_address=(body.place_address or "").strip()[:300] or None,
        total_sessions=body.total_sessions,
        interval_days=body.interval_days,
        start_date=start,
        notes=(body.notes or "").strip() or None,
        status="active",
    )
    db.add(course)
    await db.flush()
    for i in range(1, body.total_sessions + 1):
        db.add(
            CareCourseSession(
                course_id=course.id,
                session_number=i,
                scheduled_date=start + timedelta(days=(i - 1) * (body.interval_days or 0)),
                status="pending",
            )
        )
    await db.flush()
    await db.refresh(course, ["sessions"])
    return course


async def json_delete_course(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID) -> None:
    await delete_course(db, user_id, course_id)
