"""Personal Care API (M3 Personal Suite, Шаг 15, ROADMAP §7 4B).

Уход, косметика, гигиена, процедуры и внешность (PRODUCT_OVERVIEW §8) —
**relief-only** (PD-013): никакой игровой интеграции, никаких штрафов.
Все записи Private Record (DATA_LIFECYCLE.md): отдельное удаление,
связи с Cycle — снимок расчётной фазы (не факт, §9.4); медиа — через
owner_type=care_entry (owner-scoped).

Страницы:
- GET  /care                    — каталог процедур + журнал ухода
- POST /care/routines           — создать процедуру
- POST /care/routines/{id}/delete — удалить процедуру (записи — SET NULL)
- POST /care/entries            — записать факт выполнения процедуры
- POST /care/entries/{id}/media — привязать фото динамики
- POST /care/entries/{id}/delete — удалить запись

JSON API (мобильный/bearer):
- GET  /api/v2/care             — сводка + процедуры + записи
- POST /api/v2/care/routines    — создать процедуру
- POST /api/v2/care/entries     — записать факт выполнения
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.catalog import catalog_options
from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
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
from app.services.media import save_media
from app.templates_setup import templates
from app.timeutils import local_today

logger = logging.getLogger(__name__)

router = APIRouter(tags=["care"])


# ─────────────────────────────────────────────────────────────────────────────
# Cycle phase snapshot (связь Personal Care ↔ Cycle, §9.4/§16)
# ─────────────────────────────────────────────────────────────────────────────


async def _cycle_snapshot(db: AsyncSession, user_id: uuid.UUID, entry_date: date) -> tuple[str | None, int | None]:
    """Расчётная фаза Cycle на дату процедуры (снимок, не факт — §9.4)."""
    try:
        from app.api.health import _cycle_phase, _day_of_cycle
        from app.models.health import CycleEvent, CycleSettings
    except Exception:  # health may not be deployed
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


async def _care_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Краткая сводка для дашборда: процедуры за 30д, последняя, число процедур."""
    from datetime import timedelta

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
# Page
# ─────────────────────────────────────────────────────────────────────────────


async def _media_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, list[dict]]:
    """owner_ref_id → [media assets] for care photos (care_entry + care_product)."""
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


@router.get("/care", response_class=HTMLResponse)
async def care_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

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
    media = await _media_map(db, user.id)

    # Сквозной каталог (ADR-091): пикер видов процедур (домен care).
    catalog_items = await catalog_options(db, user.id, domain="care")

    # Каталог средств/косметики (Шаг 16b): позиции + счётчик использований.
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
    inventory_options = await _inventory_options(db, user.id)
    inventory_names = {i["id"]: i for i in inventory_options}
    catalog_names = {c["id"]: c["name"] for c in catalog_items}
    product_names = {str(p.id): p.name for p in products}
    product_ids_by_entry = await _entry_product_map(db, user.id)

    # Курсы процедур (Шаг 17c, ADR-095): серии сеансов с прогрессом.
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

    return templates.TemplateResponse(
        request=request,
        name="care.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
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
            "entries": [_entry_view(e, routine_names, product_ids_by_entry) for e in entries],
            "media": media,
            "catalog_items": catalog_items,
            "products": [_product_view(p, usage_by_product, inventory_names, catalog_names) for p in products],
            "product_names": product_names,
            "inventory_options": inventory_options,
            "care_areas": list(CARE_AREAS),
            "care_kinds": list(CARE_KINDS),
            "care_product_categories": list(CARE_PRODUCT_CATEGORIES),
            "scales": list(SCALE_1_5),
        },
    )


def _product_view(
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


async def _entry_product_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, list[str]]:
    """entry_id → [product_ids] for the care log (all entries of the user)."""
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


def _entry_view(
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


# ─────────────────────────────────────────────────────────────────────────────
# Form handlers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_int(raw: str, field_name: str, minimum: int = 0, maximum: int = 10000) -> int | None:
    if not raw.strip():
        return None
    try:
        v = int(raw)
    except ValueError:
        raise HTTPException(400, f"Invalid {field_name}") from None
    if v < minimum or v > maximum:
        raise HTTPException(400, f"Invalid {field_name} (out of range)")
    return v


def _parse_date(raw: str, field_name: str) -> date | None:
    if not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise HTTPException(400, f"Invalid {field_name} (ISO 8601)") from None


async def _validate_routine(db: AsyncSession, routine_id: str, user_id: uuid.UUID) -> uuid.UUID | None:
    if not routine_id.strip():
        return None
    try:
        rid = uuid.UUID(routine_id.strip())
    except ValueError:
        raise HTTPException(400, "Invalid routine_id") from None
    routine = (
        await db.execute(select(CareRoutine).where(CareRoutine.id == rid, CareRoutine.user_id == user_id))
    ).scalar_one_or_none()
    if routine is None:
        raise HTTPException(400, "Routine not found")
    return rid


async def _resolve_catalog_item(
    db: AsyncSession, catalog_item_id: str | uuid.UUID | None, user_id: uuid.UUID
) -> ActivityCatalogItem | None:
    """Validate catalog reference (system or owned by user)."""
    if not catalog_item_id:
        return None
    try:
        cid = uuid.UUID(str(catalog_item_id))
    except ValueError:
        raise HTTPException(400, "Invalid catalog_item_id") from None
    item = (
        await db.execute(
            select(ActivityCatalogItem).where(
                ActivityCatalogItem.id == cid,
                ActivityCatalogItem.owner_id.is_(None) | (ActivityCatalogItem.owner_id == user_id),
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(400, "Catalog item not found")
    return item


async def _resolve_inventory_item(
    db: AsyncSession, inventory_item_id: str | uuid.UUID | None, user_id: uuid.UUID
) -> InventoryItem | None:
    """Validate inventory reference (must belong to the user)."""
    if not inventory_item_id:
        return None
    try:
        iid = uuid.UUID(str(inventory_item_id))
    except ValueError:
        raise HTTPException(400, "Invalid inventory_item_id") from None
    item = (
        await db.execute(select(InventoryItem).where(InventoryItem.id == iid, InventoryItem.user_id == user_id))
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(400, "Inventory item not found")
    return item


async def _resolve_products(
    db: AsyncSession, product_ids: list[str | uuid.UUID] | None, user_id: uuid.UUID
) -> list[uuid.UUID]:
    """Validate product references (must belong to the user); dedupe preserving order."""
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
            raise HTTPException(400, "Invalid product_id") from None
        if pid in seen:
            continue
        product = (
            await db.execute(select(CareProduct).where(CareProduct.id == pid, CareProduct.user_id == user_id))
        ).scalar_one_or_none()
        if product is None:
            raise HTTPException(400, "Product not found")
        seen.add(pid)
        out.append(pid)
    return out


async def _inventory_options(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Инвентарь для пикера средств (активные позиции, без мигрированных в лекарства)."""
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


async def _entry_product_ids(db: AsyncSession, entry_id: uuid.UUID) -> list[str]:
    """Product ids bound to a care entry (for view/JSON)."""
    rows = (
        (await db.execute(select(CareEntryProduct.product_id).where(CareEntryProduct.entry_id == entry_id)))
        .scalars()
        .all()
    )
    return [str(r) for r in rows]


async def _set_entry_products(db: AsyncSession, entry_id: uuid.UUID, product_ids: list[uuid.UUID]) -> None:
    """Replace the product set bound to a care entry (join rows, CASCADE)."""
    from sqlalchemy import delete

    await db.execute(delete(CareEntryProduct).where(CareEntryProduct.entry_id == entry_id))
    for pid in product_ids:
        db.add(CareEntryProduct(entry_id=entry_id, product_id=pid))


async def _set_routine_products(db: AsyncSession, routine_id: uuid.UUID, product_ids: list[uuid.UUID]) -> None:
    """Replace the recommended product set for a routine (care_routine_products)."""
    from sqlalchemy import delete

    await db.execute(delete(CareRoutineProduct).where(CareRoutineProduct.routine_id == routine_id))
    for pid in product_ids:
        db.add(CareRoutineProduct(routine_id=routine_id, product_id=pid))


@router.post("/care/routines")
async def add_routine(
    request: Request,
    name: str = Form(...),
    area: str = Form(default="other"),
    kind: str = Form(default="home"),
    place_name: str = Form(default=""),
    place_address: str = Form(default=""),
    frequency_days: str = Form(default=""),
    notes: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    product_ids: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    if area not in CARE_AREAS:
        area = "other"
    if kind not in CARE_KINDS:
        kind = "home"
    catalog_item = await _resolve_catalog_item(db, catalog_item_id, user.id)
    resolved_products = await _resolve_products(db, product_ids, user.id)
    routine = CareRoutine(
        user_id=user.id,
        name=name,
        catalog_item_id=catalog_item.id if catalog_item else None,
        area=area,
        kind=kind,
        place_name=(place_name or "").strip()[:200] or None,
        place_address=(place_address or "").strip()[:300] or None,
        frequency_days=_parse_int(frequency_days, "frequency_days", minimum=1, maximum=3650),
        notes=(notes or "").strip() or None,
    )
    db.add(routine)
    await db.flush()
    await _set_routine_products(db, routine.id, resolved_products)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/routines/{routine_id}/delete")
async def delete_routine(
    request: Request,
    routine_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    routine = (
        await db.execute(select(CareRoutine).where(CareRoutine.id == routine_id, CareRoutine.user_id == user.id))
    ).scalar_one_or_none()
    if routine is None:
        raise HTTPException(404, "Routine not found")
    # записи сохраняются, ссылка обнуляется (SET NULL на уровне приложения)
    entries = (
        (await db.execute(select(CareEntry).where(CareEntry.user_id == user.id, CareEntry.routine_id == routine_id)))
        .scalars()
        .all()
    )
    for e in entries:
        e.routine_id = None
    # join-строки рекомендуемых средств удаляются на уровне приложения + CASCADE в БД
    from sqlalchemy import delete

    await db.execute(delete(CareRoutineProduct).where(CareRoutineProduct.routine_id == routine_id))
    await db.delete(routine)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/products")
async def add_product(
    request: Request,
    name: str = Form(...),
    category: str = Form(default="other"),
    brand: str = Form(default=""),
    notes: str = Form(default=""),
    inventory_item_id: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    quantity: str = Form(default=""),
    expiry_date: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    if category not in CARE_PRODUCT_CATEGORIES:
        category = "other"
    inventory_item = await _resolve_inventory_item(db, inventory_item_id, user.id)
    catalog_item = await _resolve_catalog_item(db, catalog_item_id, user.id)
    product = CareProduct(
        user_id=user.id,
        name=name,
        category=category,
        brand=(brand or "").strip()[:120] or None,
        notes=(notes or "").strip() or None,
        inventory_item_id=inventory_item.id if inventory_item else None,
        catalog_item_id=catalog_item.id if catalog_item else None,
        quantity=_parse_int(quantity, "quantity", minimum=0, maximum=100000) or 0,
        expiry_date=_parse_date(expiry_date, "expiry_date"),
    )
    db.add(product)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/products/{product_id}/delete")
async def delete_product(
    request: Request,
    product_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = (
        await db.execute(select(CareProduct).where(CareProduct.id == product_id, CareProduct.user_id == user.id))
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(404, "Product not found")
    # join-строки care_entry_products + care_routine_products удаляются на уровне
    # приложения (и CASCADE в БД)
    from sqlalchemy import delete

    await db.execute(delete(CareEntryProduct).where(CareEntryProduct.product_id == product_id))
    await db.execute(delete(CareRoutineProduct).where(CareRoutineProduct.product_id == product_id))
    await db.delete(product)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/entries")
async def add_entry(
    request: Request,
    entry_date: str = Form(...),
    routine_id: str = Form(default=""),
    place_name: str = Form(default=""),
    place_address: str = Form(default=""),
    duration_minutes: str = Form(default=""),
    skin_reaction: str = Form(default=""),
    notes: str = Form(default=""),
    product_ids: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        d = date.fromisoformat(entry_date.strip())
    except ValueError:
        raise HTTPException(400, "Invalid entry_date (ISO 8601)") from None

    rid = await _validate_routine(db, routine_id, user.id)
    reaction = _parse_scale(skin_reaction, "skin_reaction") if skin_reaction.strip() else None
    resolved_products = await _resolve_products(db, product_ids, user.id)

    cycle_phase, cycle_day = await _cycle_snapshot(db, user.id, d)

    entry = CareEntry(
        user_id=user.id,
        routine_id=rid,
        entry_date=d,
        place_name=(place_name or "").strip()[:200] or None,
        place_address=(place_address or "").strip()[:300] or None,
        duration_minutes=_parse_int(duration_minutes, "duration_minutes"),
        skin_reaction=reaction,
        notes=(notes or "").strip() or None,
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    db.add(entry)
    await db.flush()
    await _set_entry_products(db, entry.id, resolved_products)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


def _parse_scale(raw: str, field_name: str) -> int:
    try:
        v = int(raw)
    except ValueError:
        raise HTTPException(400, f"Invalid {field_name} (1-5)") from None
    if v not in SCALE_1_5:
        raise HTTPException(400, f"Invalid {field_name} (1-5)")
    return v


@router.post("/care/entries/{entry_id}/media")
async def add_entry_media(
    request: Request,
    entry_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Привязать фото динамики к записи ухода (owner_type=care_entry, owner-scoped)."""
    entry = (
        await db.execute(select(CareEntry).where(CareEntry.id == entry_id, CareEntry.user_id == user.id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Care entry not found")

    info = await save_media(file)
    asset = MediaAsset(
        owner_id=user.id,
        owner_type="care_entry",
        owner_ref_id=entry.id,
        state="ready",
        file_path=info["file_path"],
        thumbnail_path=info["thumbnail_path"],
        original_filename=info["original_filename"],
        mime_type=info["mime_type"],
        file_size_bytes=info["file_size_bytes"],
        sha256_hex=info["sha256_hex"],
        width=info["width"],
        height=info["height"],
        caption=(caption or "").strip()[:500] or None,
    )
    db.add(asset)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/products/{product_id}/media")
async def add_product_media(
    request: Request,
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Привязать фото средства (owner_type=care_product, owner-scoped)."""
    product = (
        await db.execute(select(CareProduct).where(CareProduct.id == product_id, CareProduct.user_id == user.id))
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(404, "Care product not found")

    info = await save_media(file)
    asset = MediaAsset(
        owner_id=user.id,
        owner_type="care_product",
        owner_ref_id=product.id,
        state="ready",
        file_path=info["file_path"],
        thumbnail_path=info["thumbnail_path"],
        original_filename=info["original_filename"],
        mime_type=info["mime_type"],
        file_size_bytes=info["file_size_bytes"],
        sha256_hex=info["sha256_hex"],
        width=info["width"],
        height=info["height"],
        caption=(caption or "").strip()[:500] or None,
    )
    db.add(asset)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/entries/{entry_id}/delete")
async def delete_entry(
    request: Request,
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = (
        await db.execute(select(CareEntry).where(CareEntry.id == entry_id, CareEntry.user_id == user.id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Care entry not found")
    await db.delete(entry)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────

json_router = APIRouter(prefix="/api/v2/care", tags=["care"])


@router.get("/care/builder", response_class=HTMLResponse)
async def care_builder_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Interactive Care & Aftercare Kit Builder page (Step 36)."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="care_builder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "care",
        },
    )


@json_router.get("")
async def json_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    routines = (
        (await db.execute(select(CareRoutine).where(CareRoutine.user_id == user.id).order_by(CareRoutine.name.asc())))
        .scalars()
        .all()
    )
    entries = (
        (await db.execute(select(CareEntry).where(CareEntry.user_id == user.id).order_by(CareEntry.entry_date.desc())))
        .scalars()
        .all()
    )
    products = (
        (await db.execute(select(CareProduct).where(CareProduct.user_id == user.id).order_by(CareProduct.name.asc())))
        .scalars()
        .all()
    )
    product_ids_by_entry = await _entry_product_map(db, user.id)
    return {
        "total_entries": len(entries),
        "routines": [_routine_json(r) for r in routines],
        "entries": [_entry_json(e, product_ids_by_entry) for e in entries[:50]],
        "products": [_product_json(p) for p in products],
    }


def _routine_json(r: CareRoutine) -> dict:
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


def _product_json(p: CareProduct) -> dict:
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


def _entry_json(e: CareEntry, product_ids_by_entry: dict[str, list[str]] | None = None) -> dict:
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


@json_router.post("/routines", status_code=201)
async def json_add_routine(
    body: RoutineBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    area = body.area if body.area in CARE_AREAS else "other"
    kind = body.kind if body.kind in CARE_KINDS else "home"
    catalog_item = await _resolve_catalog_item(db, body.catalog_item_id, user.id)
    resolved_products = await _resolve_products(db, body.product_ids, user.id)
    routine = CareRoutine(
        user_id=user.id,
        name=name,
        catalog_item_id=catalog_item.id if catalog_item else None,
        area=area,
        kind=kind,
        place_name=(body.place_name or "").strip()[:200] or None,
        place_address=(body.place_address or "").strip()[:300] or None,
        frequency_days=body.frequency_days,
        notes=(body.notes or "").strip() or None,
    )
    db.add(routine)
    await db.flush()
    await _set_routine_products(db, routine.id, resolved_products)
    await db.flush()
    # `products` — lazy="selectin": для только что созданной рутины нужен
    # явный refresh, иначе async-контекст бросит MissingGreenlet.
    await db.refresh(routine, ["products"])
    return _routine_json(routine)


class EntryBody(BaseModel):
    entry_date: date
    routine_id: uuid.UUID | None = None
    place_name: str | None = Field(default=None, max_length=200)
    place_address: str | None = Field(default=None, max_length=300)
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    skin_reaction: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    product_ids: list[uuid.UUID] = Field(default_factory=list)


@json_router.post("/entries", status_code=201)
async def json_add_entry(
    body: EntryBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rid = None
    if body.routine_id is not None:
        routine = (
            await db.execute(
                select(CareRoutine).where(CareRoutine.id == body.routine_id, CareRoutine.user_id == user.id)
            )
        ).scalar_one_or_none()
        if routine is None:
            raise HTTPException(400, "Routine not found")
        rid = body.routine_id

    resolved_products = await _resolve_products(db, body.product_ids, user.id)

    cycle_phase, cycle_day = await _cycle_snapshot(db, user.id, body.entry_date)

    entry = CareEntry(
        user_id=user.id,
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
    await _set_entry_products(db, entry.id, resolved_products)
    await db.flush()
    return _entry_json(entry, {str(entry.id): [str(p) for p in resolved_products]})


@json_router.delete("/routines/{routine_id}", status_code=204)
async def json_delete_routine(
    routine_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить процедуру (JSON) — записи сохраняются, ссылка обнуляется."""
    routine = (
        await db.execute(select(CareRoutine).where(CareRoutine.id == routine_id, CareRoutine.user_id == user.id))
    ).scalar_one_or_none()
    if routine is None:
        raise HTTPException(404, "Routine not found")
    entries = (
        (await db.execute(select(CareEntry).where(CareEntry.user_id == user.id, CareEntry.routine_id == routine_id)))
        .scalars()
        .all()
    )
    for e in entries:
        e.routine_id = None
    from sqlalchemy import delete

    await db.execute(delete(CareRoutineProduct).where(CareRoutineProduct.routine_id == routine_id))
    await db.delete(routine)
    await db.flush()
    return None


@json_router.delete("/entries/{entry_id}", status_code=204)
async def json_delete_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить запись ухода (JSON) — join-строки средств чистятся явно."""
    entry = (
        await db.execute(select(CareEntry).where(CareEntry.id == entry_id, CareEntry.user_id == user.id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Care entry not found")
    from sqlalchemy import delete

    await db.execute(delete(CareEntryProduct).where(CareEntryProduct.entry_id == entry_id))
    await db.delete(entry)
    await db.flush()
    return None


@json_router.get("/products")
async def json_list_products(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список средств/косметики — для мобильного клиента (owner-scoped)."""
    products = (
        (
            await db.execute(
                select(CareProduct).where(CareProduct.user_id == user.id).order_by(CareProduct.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_product_json(p) for p in products]


class ProductBody(BaseModel):
    name: str
    category: str = "other"
    brand: str | None = None
    notes: str | None = None
    inventory_item_id: uuid.UUID | None = None
    catalog_item_id: uuid.UUID | None = None
    quantity: int = Field(default=0, ge=0, le=100000)
    expiry_date: date | None = None


@json_router.post("/products", status_code=201)
async def json_add_product(
    body: ProductBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    category = body.category if body.category in CARE_PRODUCT_CATEGORIES else "other"
    inventory_item = await _resolve_inventory_item(db, body.inventory_item_id, user.id)
    catalog_item = await _resolve_catalog_item(db, body.catalog_item_id, user.id)
    product = CareProduct(
        user_id=user.id,
        name=name,
        category=category,
        brand=(body.brand or "").strip()[:120] or None,
        notes=(body.notes or "").strip() or None,
        inventory_item_id=inventory_item.id if inventory_item else None,
        catalog_item_id=catalog_item.id if catalog_item else None,
        quantity=body.quantity,
        expiry_date=body.expiry_date,
    )
    db.add(product)
    await db.flush()
    return _product_json(product)


@json_router.delete("/products/{product_id}", status_code=204)
async def json_delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product = (
        await db.execute(select(CareProduct).where(CareProduct.id == product_id, CareProduct.user_id == user.id))
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(404, "Product not found")
    from sqlalchemy import delete

    await db.execute(delete(CareEntryProduct).where(CareEntryProduct.product_id == product_id))
    await db.execute(delete(CareRoutineProduct).where(CareRoutineProduct.product_id == product_id))
    await db.delete(product)
    await db.flush()
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Procedure courses (Шаг 17c, ADR-095) — серии сеансов
# ─────────────────────────────────────────────────────────────────────────────


def _course_json(c: CareCourse) -> dict:
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


@router.post("/care/courses")
async def add_course(
    request: Request,
    name: str = Form(...),
    area: str = Form(default="other"),
    place_name: str = Form(default=""),
    place_address: str = Form(default=""),
    total_sessions: str = Form(default="1"),
    interval_days: str = Form(default=""),
    start_date: str = Form(default=""),
    notes: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать курс процедур — генерирует N сеансов с интервалом."""
    name = name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    if area not in CARE_AREAS:
        area = "other"
    total = _parse_int(total_sessions, "total_sessions", minimum=1, maximum=200) or 1
    interval = _parse_int(interval_days, "interval_days", minimum=1, maximum=3650)
    start = None
    if start_date.strip():
        try:
            start = date.fromisoformat(start_date.strip())
        except ValueError as exc:
            raise HTTPException(400, "Invalid start_date (ISO 8601)") from exc
    if start is None:
        start = local_today()
    catalog_item = await _resolve_catalog_item(db, catalog_item_id, user.id)

    course = CareCourse(
        user_id=user.id,
        name=name,
        catalog_item_id=catalog_item.id if catalog_item else None,
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
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/courses/{course_id}/delete")
async def delete_course(
    request: Request,
    course_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = (
        await db.execute(select(CareCourse).where(CareCourse.id == course_id, CareCourse.user_id == user.id))
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(404, "Course not found")
    await db.delete(course)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/course-sessions/{session_id}/done")
async def mark_session_done(
    request: Request,
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = (
        await db.execute(
            select(CareCourseSession)
            .join(CareCourse, CareCourse.id == CareCourseSession.course_id)
            .where(CareCourseSession.id == session_id, CareCourse.user_id == user.id)
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(404, "Course session not found")
    session.status = "done"
    session.completed_at = _now_utc()
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/course-sessions/{session_id}/skip")
async def mark_session_skipped(
    request: Request,
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = (
        await db.execute(
            select(CareCourseSession)
            .join(CareCourse, CareCourse.id == CareCourseSession.course_id)
            .where(CareCourseSession.id == session_id, CareCourse.user_id == user.id)
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(404, "Course session not found")
    session.status = "skipped"
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@json_router.get("/courses")
async def json_list_courses(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список курсов процедур (серии сеансов) — для мобильного клиента."""
    courses = (
        (
            await db.execute(
                select(CareCourse).where(CareCourse.user_id == user.id).order_by(CareCourse.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_course_json(c) for c in courses]


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


@json_router.post("/courses", status_code=201)
async def json_add_course(
    body: CourseBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    area = body.area if body.area in CARE_AREAS else "other"
    start = body.start_date or local_today()
    catalog_item = await _resolve_catalog_item(db, body.catalog_item_id, user.id)
    course = CareCourse(
        user_id=user.id,
        name=name,
        catalog_item_id=catalog_item.id if catalog_item else None,
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
    return _course_json(course)


@json_router.delete("/courses/{course_id}", status_code=204)
async def json_delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить курс процедур (сеансы удаляются каскадом) — для мобильного клиента."""
    course = (
        await db.execute(select(CareCourse).where(CareCourse.id == course_id, CareCourse.user_id == user.id))
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(404, "Course not found")
    await db.delete(course)
    await db.flush()
    return None


async def _owned_course_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID):
    session = (
        await db.execute(
            select(CareCourseSession)
            .join(CareCourse, CareCourse.id == CareCourseSession.course_id)
            .where(CareCourseSession.id == session_id, CareCourse.user_id == user_id)
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(404, "Course session not found")
    return session


@json_router.post("/course-sessions/{session_id}/done")
async def json_mark_course_session_done(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await _owned_course_session(db, user.id, session_id)
    session.status = "done"
    session.completed_at = _now_utc()
    await db.flush()
    return {"id": str(session.id), "status": session.status, "completed_at": session.completed_at.isoformat()}


@json_router.post("/course-sessions/{session_id}/skip")
async def json_mark_course_session_skipped(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await _owned_course_session(db, user.id, session_id)
    session.status = "skipped"
    session.completed_at = None
    await db.flush()
    return {"id": str(session.id), "status": session.status, "completed_at": None}


def _now_utc():
    from datetime import UTC
    from datetime import datetime as _dt

    return _dt.now(UTC)


@json_router.post("/aftercare/generate")
async def json_generate_aftercare(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generates Aftercare recovery protocol via LLM Assistant (Step 23)."""
    from app.llm.pipeline.aftercare import generate_aftercare_guidance
    from app.services.llm_provider import get_active_llm_config

    llm_config = await get_active_llm_config(db, user.id)
    if not llm_config:
        raise HTTPException(400, "LLM provider config is required for Aftercare AI Assistant")

    locale = detect_locale(request, user.locale)
    res = await generate_aftercare_guidance(db, user.id, llm_config, locale=locale)
    return res
