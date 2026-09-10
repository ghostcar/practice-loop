"""Personal Care — Page context builder."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.care import (
    CARE_AREAS,
    CARE_KINDS,
    CARE_PRODUCT_CATEGORIES,
    SCALE_1_5,
    CareCourse,
    CareEntry,
    CareEntryProduct,
    CareProduct,
    CareRoutine,
)
from app.models.user import User
from app.timeutils import local_today

from app.services.care.helpers import resolve_products
from app.services.care.relations import set_entry_products, set_routine_products
from app.services.care.serializers import entry_view, product_view
from app.services.care.summary import entry_product_map, inventory_options, media_map


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
