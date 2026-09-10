"""Personal Care — JSON API wrappers."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.care import (
    CARE_AREAS,
    CARE_KINDS,
    CARE_PRODUCT_CATEGORIES,
    CareCourse,
    CareCourseSession,
    CareEntry,
    CareEntryProduct,
    CareProduct,
    CareRoutine,
)
from app.services.errors import NotFoundError
from app.timeutils import local_today

from app.services.care.helpers import resolve_catalog_item, resolve_inventory_item, resolve_products
from app.services.care.relations import cycle_snapshot, set_entry_products, set_routine_products
from app.services.care.schemas import CourseBody, EntryBody, ProductBody, RoutineBody
from app.services.care.serializers import course_json, entry_json, product_json, routine_json
from app.services.care.summary import entry_product_map


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
    from app.services.care.crud import delete_routine
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
    from app.services.care.crud import delete_product
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
    from app.services.care.crud import delete_course
    await delete_course(db, user_id, course_id)
