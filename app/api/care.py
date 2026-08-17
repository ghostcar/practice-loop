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
from datetime import date

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
from app.models.care import CARE_AREAS, CARE_KINDS, SCALE_1_5, CareEntry, CareRoutine
from app.models.catalog import ActivityCatalogItem
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
        (await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))).scalar_one_or_none()
    )
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
    total = (
        await db.execute(select(func.count(CareEntry.id)).where(CareEntry.user_id == user_id))
    ).scalar() or 0
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
    """entry_id → [media assets] for care photos (owner_type=care_entry)."""
    rows = (
        (
            await db.execute(
                select(MediaAsset)
                .where(MediaAsset.owner_id == user_id, MediaAsset.owner_type == "care_entry")
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
        (
            await db.execute(
                select(CareRoutine).where(CareRoutine.user_id == user.id).order_by(CareRoutine.name.asc())
            )
        )
        .scalars()
        .all()
    )
    routine_names = {str(r.id): r.name for r in routines}
    entries = (
        (
            await db.execute(
                select(CareEntry).where(CareEntry.user_id == user.id).order_by(CareEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    media = await _media_map(db, user.id)

    # Сквозной каталог (ADR-091): пикер видов процедур (домен care).
    catalog_items = await catalog_options(db, user.id, domain="care")

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
            "routines": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "area": r.area,
                    "kind": r.kind,
                    "frequency_days": r.frequency_days,
                    "notes": r.notes,
                    "entries_count": sum(1 for e in entries if e.routine_id == r.id),
                }
                for r in routines
            ],
            "entries": [_entry_view(e, routine_names) for e in entries],
            "media": media,
            "catalog_items": catalog_items,
            "care_areas": list(CARE_AREAS),
            "care_kinds": list(CARE_KINDS),
            "scales": list(SCALE_1_5),
        },
    )


def _entry_view(e: CareEntry, routine_names: dict[str, str]) -> dict:
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "routine_id": str(e.routine_id) if e.routine_id else None,
        "routine_name": routine_names.get(str(e.routine_id)) if e.routine_id else None,
        "duration_minutes": e.duration_minutes,
        "skin_reaction": e.skin_reaction,
        "notes": e.notes,
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
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


@router.post("/care/routines")
async def add_routine(
    request: Request,
    name: str = Form(...),
    area: str = Form(default="other"),
    kind: str = Form(default="home"),
    frequency_days: str = Form(default=""),
    notes: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
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
    routine = CareRoutine(
        user_id=user.id,
        name=name,
        catalog_item_id=catalog_item.id if catalog_item else None,
        area=area,
        kind=kind,
        frequency_days=_parse_int(frequency_days, "frequency_days", minimum=1, maximum=3650),
        notes=(notes or "").strip() or None,
    )
    db.add(routine)
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
        (
            await db.execute(
                select(CareEntry).where(CareEntry.user_id == user.id, CareEntry.routine_id == routine_id)
            )
        )
        .scalars()
        .all()
    )
    for e in entries:
        e.routine_id = None
    await db.delete(routine)
    await db.flush()
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/entries")
async def add_entry(
    request: Request,
    entry_date: str = Form(...),
    routine_id: str = Form(default=""),
    duration_minutes: str = Form(default=""),
    skin_reaction: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        d = date.fromisoformat(entry_date.strip())
    except ValueError:
        raise HTTPException(400, "Invalid entry_date (ISO 8601)") from None

    rid = await _validate_routine(db, routine_id, user.id)
    reaction = _parse_scale(skin_reaction, "skin_reaction") if skin_reaction.strip() else None

    cycle_phase, cycle_day = await _cycle_snapshot(db, user.id, d)

    entry = CareEntry(
        user_id=user.id,
        routine_id=rid,
        entry_date=d,
        duration_minutes=_parse_int(duration_minutes, "duration_minutes"),
        skin_reaction=reaction,
        notes=(notes or "").strip() or None,
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    db.add(entry)
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


@json_router.get("")
async def json_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    routines = (
        (
            await db.execute(
                select(CareRoutine).where(CareRoutine.user_id == user.id).order_by(CareRoutine.name.asc())
            )
        )
        .scalars()
        .all()
    )
    entries = (
        (
            await db.execute(
                select(CareEntry).where(CareEntry.user_id == user.id).order_by(CareEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "total_entries": len(entries),
        "routines": [_routine_json(r) for r in routines],
        "entries": [_entry_json(e) for e in entries[:50]],
    }


def _routine_json(r: CareRoutine) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "catalog_item_id": str(r.catalog_item_id) if r.catalog_item_id else None,
        "area": r.area,
        "kind": r.kind,
        "frequency_days": r.frequency_days,
        "notes": r.notes,
    }


def _entry_json(e: CareEntry) -> dict:
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "routine_id": str(e.routine_id) if e.routine_id else None,
        "duration_minutes": e.duration_minutes,
        "skin_reaction": e.skin_reaction,
        "notes": e.notes,
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
    }


class RoutineBody(BaseModel):
    name: str
    catalog_item_id: uuid.UUID | None = None
    area: str = "other"
    kind: str = "home"
    frequency_days: int | None = Field(default=None, ge=1, le=3650)
    notes: str | None = None


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
    routine = CareRoutine(
        user_id=user.id,
        name=name,
        catalog_item_id=catalog_item.id if catalog_item else None,
        area=area,
        kind=kind,
        frequency_days=body.frequency_days,
        notes=(body.notes or "").strip() or None,
    )
    db.add(routine)
    await db.flush()
    return _routine_json(routine)


class EntryBody(BaseModel):
    entry_date: date
    routine_id: uuid.UUID | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    skin_reaction: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None


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

    cycle_phase, cycle_day = await _cycle_snapshot(db, user.id, body.entry_date)

    entry = CareEntry(
        user_id=user.id,
        routine_id=rid,
        entry_date=body.entry_date,
        duration_minutes=body.duration_minutes,
        skin_reaction=body.skin_reaction,
        notes=(body.notes or "").strip() or None,
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    db.add(entry)
    await db.flush()
    return _entry_json(entry)
