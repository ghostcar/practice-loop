"""Personal Care — CRUD operations."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

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
    CareRoutineProduct,
)
from app.models.media import MediaAsset
from app.services.errors import NotFoundError
from app.timeutils import local_today

from app.services.care.helpers import (
    _now_utc,
    parse_date,
    parse_int,
    parse_scale,
    resolve_catalog_item,
    resolve_inventory_item,
    resolve_products,
    validate_routine,
)
from app.services.care.relations import cycle_snapshot, set_entry_products, set_routine_products


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
