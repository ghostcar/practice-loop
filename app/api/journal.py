"""Sexual Journal API (M3 Personal Suite, Шаг 14, ROADMAP §7 4A).

Приватная запись фактической сексуальной жизни (PRODUCT_OVERVIEW §7) —
**relief-only** (PD-013): никакой игровой интеграции, никаких штрафов.
Все записи — Private Record (DATA_LIFECYCLE.md): отдельное удаление,
связи с Tracker/Timer/Health — по ID без раскрытия (мягкие ссылки, без FK).

Связи (Шаг 14b):
- **Tracker**: ``activity_log_id`` — запись может быть результатом задачи;
- **Timer**: ``slot_occurrence_id`` — окно таймера для плановой активности
  авто-создаёт draft-запись (``source=timer_slot``, ``status=draft``), детали
  пользователь обязан внести при закрытии (``POST .../complete``);
- **Media**: фото привязывается через ``POST /journal/entries/{id}/media``
  (owner_type=journal_entry, owner-scoped).

Страницы:
- GET  /journal                     — записи + псевдонимы + pending-детали + медиа
- POST /journal/entries             — создать запись (снимок фазы Cycle)
- POST /journal/entries/{id}/complete — заполнить детали draft-записи (при закрытии)
- POST /journal/entries/{id}/media  — привязать фото к записи
- POST /journal/entries/{id}/delete — удалить запись
- POST /journal/partners            — создать псевдоним партнёра
- POST /journal/partners/{id}/delete — удалить псевдоним

JSON API (мобильный/bearer):
- GET  /api/v2/journal              — сводка + записи + партнёры
- POST /api/v2/journal/entries      — создать запись
- POST /api/v2/journal/entries/{id}/complete — заполнить детали draft
- POST /api/v2/journal/partners     — создать псевдоним
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
from app.models.activity_log import ActivityLog
from app.models.catalog import ActivityCatalogItem
from app.models.journal import (
    JOURNAL_SOURCES,
    JOURNAL_STATUSES,
    PROTECTION_TYPES,
    REACTION_CHOICES,
    SCALE_1_5,
    JournalEntry,
    JournalPartner,
)
from app.models.media import MediaAsset
from app.models.user import User
from app.services.media import save_media
from app.templates_setup import templates
from app.timeutils import local_today

logger = logging.getLogger(__name__)

router = APIRouter(tags=["journal"])


# ─────────────────────────────────────────────────────────────────────────────
# Cycle phase snapshot (связь Sexual Journal ↔ Cycle, PRODUCT_OVERVIEW §16)
# ─────────────────────────────────────────────────────────────────────────────


async def _cycle_snapshot(db: AsyncSession, user_id: uuid.UUID, entry_date: date) -> tuple[str | None, int | None]:
    """Расчётная фаза Cycle на дату записи (снимок, не факт — §9.4).

    Возвращает (phase, day_of_cycle). Мягкая связь по ID без раскрытия
    (DATA_LIFECYCLE.md). Если Cycle недоступен — (None, None).
    """
    try:
        from app.api.health import _cycle_phase, _day_of_cycle
        from app.models.health import CycleEvent, CycleSettings
    except Exception:  # health may not be deployed
        return None, None
    settings = (select(CycleSettings)).where(CycleSettings.user_id == user_id)
    settings_row = (await db.execute(settings)).scalar_one_or_none()
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
# Timer slot → auto journal entry (Шаг 14b)
# ─────────────────────────────────────────────────────────────────────────────


async def ensure_timer_slot_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    slot_occurrence_id: uuid.UUID,
    entry_date: date,
) -> JournalEntry | None:
    """Idempotently create a draft journal entry for an opened timer slot.

    Called from the Timer open flow (window opened for planned sexual activity).
    Returns the existing draft if already created. Journal may not be deployed —
    in that case returns None without failing the Timer action.
    """
    existing = (
        await db.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == user_id,
                JournalEntry.slot_occurrence_id == slot_occurrence_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    cycle_phase, cycle_day = await _cycle_snapshot(db, user_id, entry_date)
    entry = JournalEntry(
        user_id=user_id,
        entry_date=entry_date,
        status="draft",
        source="timer_slot",
        timer_session_id=session_id,
        slot_occurrence_id=slot_occurrence_id,
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_pending_slot_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    slot_occurrence_id: uuid.UUID,
) -> JournalEntry | None:
    """Return the draft (pending details) journal entry for a closed slot, if any."""
    return (
        await db.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == user_id,
                JournalEntry.slot_occurrence_id == slot_occurrence_id,
                JournalEntry.status == "draft",
            )
        )
    ).scalar_one_or_none()


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard summary (relief-only, informational)
# ─────────────────────────────────────────────────────────────────────────────


async def _journal_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Краткая сводка для дашборда: число записей за 30 дней, последняя запись, ср. удовлетворённость."""
    from datetime import timedelta

    today = local_today()
    since = today - timedelta(days=30)
    rows = (
        (
            await db.execute(
                select(JournalEntry)
                .where(JournalEntry.user_id == user_id, JournalEntry.entry_date >= since)
                .order_by(JournalEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    total = (
        await db.execute(select(func.count(JournalEntry.id)).where(JournalEntry.user_id == user_id))
    ).scalar() or 0
    pending = (
        await db.execute(
            select(func.count(JournalEntry.id)).where(
                JournalEntry.user_id == user_id, JournalEntry.status == "draft"
            )
        )
    ).scalar() or 0
    satisfactions = [r.satisfaction for r in rows if r.satisfaction is not None]
    last = rows[0] if rows else None
    return {
        "count_30d": len(rows),
        "total": total,
        "pending": pending,
        "last_date": last.entry_date.isoformat() if last else None,
        "last_type": last.activity_type if last else None,
        "avg_satisfaction": round(sum(satisfactions) / len(satisfactions), 1) if satisfactions else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────


async def _media_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, list[dict]]:
    """entry_id → [media assets] for journal photos (owner_type=journal_entry)."""
    rows = (
        (
            await db.execute(
                select(MediaAsset)
                .where(MediaAsset.owner_id == user_id, MediaAsset.owner_type == "journal_entry")
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


async def _activity_title_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    """activity_log_id → human title for linked Tracker tasks."""
    ids = (
        (
            await db.execute(
                select(JournalEntry.activity_log_id)
                .where(JournalEntry.user_id == user_id, JournalEntry.activity_log_id.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(ActivityLog).where(ActivityLog.id.in_(ids)))).scalars().all()
    return {str(r.id): (r.title_override or r.selected_entity_name or str(r.id)[:8]) for r in rows}


@router.get("/journal", response_class=HTMLResponse)
async def journal_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    today = local_today()
    entries = (
        (
            await db.execute(
                select(JournalEntry).where(JournalEntry.user_id == user.id).order_by(JournalEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    partners = (
        (
            await db.execute(
                select(JournalPartner).where(JournalPartner.user_id == user.id).order_by(JournalPartner.name.asc())
            )
        )
        .scalars()
        .all()
    )
    partner_names = {str(p.id): p.name for p in partners}
    media = await _media_map(db, user.id)
    activity_titles = await _activity_title_map(db, user.id)

    # Recent completed Tracker tasks for the "link to activity" select.
    recent_activities = (
        (
            await db.execute(
                select(ActivityLog)
                .where(ActivityLog.user_id == user.id)
                .order_by(ActivityLog.created_at.desc())
                .limit(30)
            )
        )
        .scalars()
        .all()
    )
    recent_activity_options = [
        {"id": str(a.id), "label": (a.title_override or a.selected_entity_name or str(a.id)[:8])[:60]}
        for a in recent_activities
    ]

    pending_entries = [e for e in entries if e.status == "draft"]
    done_entries = [e for e in entries if e.status != "draft"]

    # Сквозной каталог (ADR-091): пикер видов активности (домен journal).
    catalog_items = await catalog_options(db, user.id, domain="journal")

    # Средства/косметика (ADR-094): мультиселект средств в записи журнала.
    care_products: list[dict] = []
    try:
        from app.models.care import CareProduct

        cp_result = await db.execute(
            select(CareProduct).where(CareProduct.user_id == user.id).order_by(CareProduct.name).limit(200)
        )
        care_products = [{"id": str(p.id), "name": p.name} for p in cp_result.scalars().all()]
    except Exception:
        pass  # care module may not be deployed yet

    return templates.TemplateResponse(
        request=request,
        name="journal.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "today": today,
            "pending_entries": [_entry_view(e, partner_names) for e in pending_entries],
            "entries": [_entry_view(e, partner_names) for e in done_entries],
            "partners": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "notes": p.notes,
                    "entries_count": sum(1 for e in entries if e.partner_id == p.id),
                }
                for p in partners
            ],
            "media": media,
            "activity_titles": activity_titles,
            "recent_activities": recent_activity_options,
            "catalog_items": catalog_items,
            "care_products": care_products,
            "scales": list(SCALE_1_5),
            "protection_types": list(PROTECTION_TYPES),
            "reaction_choices": list(REACTION_CHOICES),
            "journal_statuses": list(JOURNAL_STATUSES),
            "journal_sources": list(JOURNAL_SOURCES),
        },
    )


def _entry_view(e: JournalEntry, partner_names: dict[str, str]) -> dict:
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "partner_id": str(e.partner_id) if e.partner_id else None,
        "partner_name": partner_names.get(str(e.partner_id)) if e.partner_id else None,
        "catalog_item_id": str(e.catalog_item_id) if e.catalog_item_id else None,
        "activity_type": e.activity_type,
        "duration_minutes": e.duration_minutes,
        "desire_before": e.desire_before,
        "arousal_before": e.arousal_before,
        "protection": e.protection,
        "orgasms": e.orgasms,
        "intensity": e.intensity,
        "satisfaction": e.satisfaction,
        "pleasure": e.pleasure,
        "reactions": e.reactions or [],
        "emotional_state": e.emotional_state or [],
        "care_product_ids": [str(x) for x in (e.care_product_ids or [])],
        "aftercare": e.aftercare,
        "recovery": e.recovery,
        "notes": e.notes,
        "status": e.status,
        "source": e.source,
        "activity_log_id": str(e.activity_log_id) if e.activity_log_id else None,
        "slot_occurrence_id": str(e.slot_occurrence_id) if e.slot_occurrence_id else None,
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Form handlers (commit via get_db)
# ─────────────────────────────────────────────────────────────────────────────


def _parse_scale(raw: str, field_name: str) -> int | None:
    if not raw.strip():
        return None
    try:
        v = int(raw)
    except ValueError:
        raise HTTPException(400, f"Invalid {field_name} (1-5)") from None
    if v not in SCALE_1_5:
        raise HTTPException(400, f"Invalid {field_name} (1-5)")
    return v


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


def _validate_partner(db: AsyncSession, partner_id: str, user_id: uuid.UUID) -> uuid.UUID | None:
    if not partner_id.strip():
        return None
    try:
        pid = uuid.UUID(partner_id.strip())
    except ValueError:
        raise HTTPException(400, "Invalid partner_id") from None
    return pid


async def _validate_activity_log(
    db: AsyncSession, activity_log_id: str | uuid.UUID | None, user_id: uuid.UUID
) -> uuid.UUID | None:
    """Validate that the linked Tracker task belongs to the user (мягкая ссылка по ID)."""
    if not activity_log_id:
        return None
    try:
        aid = uuid.UUID(str(activity_log_id))
    except ValueError:
        raise HTTPException(400, "Invalid activity_log_id") from None
    task = (
        await db.execute(select(ActivityLog).where(ActivityLog.id == aid, ActivityLog.user_id == user_id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(400, "Activity not found")
    return aid


async def _validate_care_products(
    db: AsyncSession, care_product_ids: str | list[uuid.UUID] | None, user_id: uuid.UUID
) -> list[str] | None:
    """Validate care product references (ADR-094) — soft links by ID.

    Accepts a comma-separated string (form) or a list of UUIDs (JSON). Returns
    None when empty, else the validated UUID list. Unknown/foreign products → 400.
    """
    if care_product_ids is None:
        return None
    if isinstance(care_product_ids, str):
        raw = [x.strip() for x in care_product_ids.split(",") if x.strip()]
        if not raw:
            return None
        try:
            parsed = [uuid.UUID(x) for x in raw]
        except ValueError:
            raise HTTPException(400, "Invalid care_product_ids") from None
    else:
        parsed = list(care_product_ids)
    if not parsed:
        return None
    from app.models.care import CareProduct

    rows = (
        await db.execute(select(CareProduct.id).where(CareProduct.id.in_(parsed), CareProduct.user_id == user_id))
    ).scalars().all()
    if len(rows) != len(set(parsed)):
        raise HTTPException(400, "One or more care products not found")
    # JSON-колонка: храним строки (UUID не сериализуется в JSON)
    return [str(x) for x in parsed]


async def _resolve_catalog_item(
    db: AsyncSession, catalog_item_id: str | uuid.UUID | None, user_id: uuid.UUID
) -> ActivityCatalogItem | None:
    """Validate catalog reference (system or owned by user) and return the item.

    The free-string ``activity_type`` is replaced by a catalog reference
    (ADR-091): the picker sends ``catalog_item_id``; the display snapshot
    ``activity_type`` is set from the item's name on save.
    """
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


async def _apply_entry_fields(
    entry: JournalEntry,
    *,
    entry_date: date,
    partner_id: uuid.UUID | None,
    catalog_item_id: uuid.UUID | None,
    activity_type: str,
    duration_minutes: int | None,
    desire_before: int | None,
    arousal_before: int | None,
    protection: str,
    orgasms: int | None,
    intensity: int | None,
    satisfaction: int | None,
    pleasure: int | None,
    reactions: list[str] | None,
    emotional_state: list[str] | None,
    aftercare: str,
    recovery: int | None,
    notes: str,
    activity_log_id: uuid.UUID | None,
    care_product_ids: list[str] | None = None,
) -> None:
    entry.entry_date = entry_date
    entry.partner_id = partner_id
    entry.catalog_item_id = catalog_item_id
    entry.care_product_ids = care_product_ids
    # снимок названия: из каталога (если выбрана запись) или свободная строка (legacy)
    entry.activity_type = (activity_type or "").strip()[:100] or None
    entry.duration_minutes = duration_minutes
    entry.desire_before = desire_before
    entry.arousal_before = arousal_before
    entry.protection = protection
    entry.orgasms = orgasms
    entry.intensity = intensity
    entry.satisfaction = satisfaction
    entry.pleasure = pleasure
    entry.reactions = reactions
    entry.emotional_state = emotional_state
    entry.aftercare = (aftercare or "").strip() or None
    entry.recovery = recovery
    entry.notes = (notes or "").strip() or None
    entry.activity_log_id = activity_log_id
    entry.status = "completed"


@router.post("/journal/entries")
async def add_entry(
    request: Request,
    entry_date: str = Form(...),
    partner_id: str = Form(default=""),
    activity_type: str = Form(default=""),
    duration_minutes: str = Form(default=""),
    desire_before: str = Form(default=""),
    arousal_before: str = Form(default=""),
    protection: str = Form(default="none"),
    orgasms: str = Form(default=""),
    intensity: str = Form(default=""),
    satisfaction: str = Form(default=""),
    pleasure: str = Form(default=""),
    reactions: str = Form(default=""),
    emotional_state: str = Form(default=""),
    aftercare: str = Form(default=""),
    recovery: str = Form(default=""),
    notes: str = Form(default=""),
    activity_log_id: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    care_product_ids: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        d = date.fromisoformat(entry_date.strip())
    except ValueError:
        raise HTTPException(400, "Invalid entry_date (ISO 8601)") from None

    partner_uuid = _validate_partner(db, partner_id, user.id)
    if partner_uuid is not None:
        partner = (
            await db.execute(
                select(JournalPartner).where(JournalPartner.id == partner_uuid, JournalPartner.user_id == user.id)
            )
        ).scalar_one_or_none()
        if partner is None:
            raise HTTPException(400, "Partner not found")

    if protection not in PROTECTION_TYPES:
        protection = "none"
    reaction_list = [x.strip() for x in reactions.split(",") if x.strip()] if reactions.strip() else None
    emotion_list = [x.strip() for x in emotional_state.split(",") if x.strip()] if emotional_state.strip() else None
    aid = await _validate_activity_log(db, activity_log_id, user.id)
    catalog_item = await _resolve_catalog_item(db, catalog_item_id, user.id)
    care_uuids = await _validate_care_products(db, care_product_ids, user.id)

    cycle_phase, cycle_day = await _cycle_snapshot(db, user.id, d)

    entry = JournalEntry(
        user_id=user.id,
        entry_date=d,
        status="completed",
        source="activity" if aid else "manual",
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    await _apply_entry_fields(
        entry,
        entry_date=d,
        partner_id=partner_uuid,
        catalog_item_id=catalog_item.id if catalog_item else None,
        activity_type=catalog_item.name if catalog_item else activity_type,
        duration_minutes=_parse_int(duration_minutes, "duration_minutes"),
        desire_before=_parse_scale(desire_before, "desire_before"),
        arousal_before=_parse_scale(arousal_before, "arousal_before"),
        protection=protection,
        orgasms=_parse_int(orgasms, "orgasms", maximum=100),
        intensity=_parse_scale(intensity, "intensity"),
        satisfaction=_parse_scale(satisfaction, "satisfaction"),
        pleasure=_parse_scale(pleasure, "pleasure"),
        reactions=reaction_list,
        emotional_state=emotion_list,
        aftercare=aftercare,
        recovery=_parse_scale(recovery, "recovery"),
        notes=notes,
        activity_log_id=aid,
        care_product_ids=care_uuids,
    )
    db.add(entry)
    await db.flush()
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/entries/{entry_id}/complete")
async def complete_entry(
    request: Request,
    entry_id: uuid.UUID,
    activity_type: str = Form(default=""),
    duration_minutes: str = Form(default=""),
    desire_before: str = Form(default=""),
    arousal_before: str = Form(default=""),
    protection: str = Form(default="none"),
    orgasms: str = Form(default=""),
    intensity: str = Form(default=""),
    satisfaction: str = Form(default=""),
    pleasure: str = Form(default=""),
    reactions: str = Form(default=""),
    emotional_state: str = Form(default=""),
    aftercare: str = Form(default=""),
    recovery: str = Form(default=""),
    notes: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    care_product_ids: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Заполнить детали draft-записи (обязательно при закрытии окна таймера)."""
    entry = (
        await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user.id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Journal entry not found")
    if entry.status != "draft":
        raise HTTPException(400, "Only draft entries can be completed")

    if protection not in PROTECTION_TYPES:
        protection = "none"
    reaction_list = [x.strip() for x in reactions.split(",") if x.strip()] if reactions.strip() else None
    emotion_list = [x.strip() for x in emotional_state.split(",") if x.strip()] if emotional_state.strip() else None
    catalog_item = await _resolve_catalog_item(db, catalog_item_id, user.id)
    care_uuids = await _validate_care_products(db, care_product_ids, user.id)

    await _apply_entry_fields(
        entry,
        entry_date=entry.entry_date,
        partner_id=entry.partner_id,
        catalog_item_id=catalog_item.id if catalog_item else None,
        activity_type=catalog_item.name if catalog_item else activity_type,
        duration_minutes=_parse_int(duration_minutes, "duration_minutes"),
        desire_before=_parse_scale(desire_before, "desire_before"),
        arousal_before=_parse_scale(arousal_before, "arousal_before"),
        protection=protection,
        orgasms=_parse_int(orgasms, "orgasms", maximum=100),
        intensity=_parse_scale(intensity, "intensity"),
        satisfaction=_parse_scale(satisfaction, "satisfaction"),
        pleasure=_parse_scale(pleasure, "pleasure"),
        reactions=reaction_list,
        emotional_state=emotion_list,
        aftercare=aftercare,
        recovery=_parse_scale(recovery, "recovery"),
        notes=notes,
        activity_log_id=entry.activity_log_id,
        care_product_ids=care_uuids,
    )
    await db.flush()
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/entries/{entry_id}/media")
async def add_entry_media(
    request: Request,
    entry_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Привязать фото к записи журнала (owner_type=journal_entry, owner-scoped)."""
    entry = (
        await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user.id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Journal entry not found")

    info = await save_media(file)
    asset = MediaAsset(
        owner_id=user.id,
        owner_type="journal_entry",
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
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/entries/{entry_id}/delete")
async def delete_entry(
    request: Request,
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = (
        await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user.id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Journal entry not found")
    await db.delete(entry)
    await db.flush()
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/partners")
async def add_partner(
    request: Request,
    name: str = Form(...),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = name.strip()[:100]
    if not name:
        raise HTTPException(400, "Name is required")
    partner = JournalPartner(user_id=user.id, name=name, notes=(notes or "").strip() or None)
    db.add(partner)
    await db.flush()
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/partners/{partner_id}/delete")
async def delete_partner(
    request: Request,
    partner_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    partner = (
        await db.execute(
            select(JournalPartner).where(JournalPartner.id == partner_id, JournalPartner.user_id == user.id)
        )
    ).scalar_one_or_none()
    if partner is None:
        raise HTTPException(404, "Partner not found")
    # Связь по ID без раскрытия (DATA_LIFECYCLE.md): записи сохраняются,
    # ссылка на псевдоним обнуляется (SET NULL) — детерминированно на уровне приложения.
    entries = (
        (
            await db.execute(
                select(JournalEntry).where(JournalEntry.user_id == user.id, JournalEntry.partner_id == partner_id)
            )
        )
        .scalars()
        .all()
    )
    for e in entries:
        e.partner_id = None
    await db.delete(partner)
    await db.flush()
    return RedirectResponse(url="/journal", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────

json_router = APIRouter(prefix="/api/v2/journal", tags=["journal"])


@json_router.get("")
async def json_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entries = (
        (
            await db.execute(
                select(JournalEntry).where(JournalEntry.user_id == user.id).order_by(JournalEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    partners = (
        (
            await db.execute(
                select(JournalPartner).where(JournalPartner.user_id == user.id).order_by(JournalPartner.name.asc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "total": len(entries),
        "pending": sum(1 for e in entries if e.status == "draft"),
        "entries": [_entry_json(e) for e in entries[:50]],
        "partners": [
            {
                "id": str(p.id),
                "name": p.name,
                "notes": p.notes,
            }
            for p in partners
        ],
    }


def _entry_json(e: JournalEntry) -> dict:
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "partner_id": str(e.partner_id) if e.partner_id else None,
        "catalog_item_id": str(e.catalog_item_id) if e.catalog_item_id else None,
        "activity_type": e.activity_type,
        "duration_minutes": e.duration_minutes,
        "desire_before": e.desire_before,
        "arousal_before": e.arousal_before,
        "protection": e.protection,
        "orgasms": e.orgasms,
        "intensity": e.intensity,
        "satisfaction": e.satisfaction,
        "pleasure": e.pleasure,
        "reactions": e.reactions or [],
        "emotional_state": e.emotional_state or [],
        "aftercare": e.aftercare,
        "recovery": e.recovery,
        "notes": e.notes,
        "status": e.status,
        "source": e.source,
        "activity_log_id": str(e.activity_log_id) if e.activity_log_id else None,
        "slot_occurrence_id": str(e.slot_occurrence_id) if e.slot_occurrence_id else None,
        "care_product_ids": [str(x) for x in (e.care_product_ids or [])],
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
    }


class EntryBody(BaseModel):
    entry_date: date
    partner_id: uuid.UUID | None = None
    catalog_item_id: uuid.UUID | None = None
    activity_type: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    desire_before: int | None = Field(default=None, ge=1, le=5)
    arousal_before: int | None = Field(default=None, ge=1, le=5)
    protection: str = "none"
    orgasms: int | None = Field(default=None, ge=0, le=100)
    intensity: int | None = Field(default=None, ge=1, le=5)
    satisfaction: int | None = Field(default=None, ge=1, le=5)
    pleasure: int | None = Field(default=None, ge=1, le=5)
    reactions: list[str] | None = None
    emotional_state: list[str] | None = None
    aftercare: str | None = None
    recovery: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    activity_log_id: uuid.UUID | None = None
    care_product_ids: list[uuid.UUID] | None = None


@json_router.post("/entries", status_code=201)
async def json_add_entry(
    body: EntryBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.partner_id is not None:
        partner = (
            await db.execute(
                select(JournalPartner).where(
                    JournalPartner.id == body.partner_id, JournalPartner.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if partner is None:
            raise HTTPException(400, "Partner not found")
    protection = body.protection if body.protection in PROTECTION_TYPES else "none"
    aid = await _validate_activity_log(db, body.activity_log_id, user.id)
    catalog_item = await _resolve_catalog_item(db, body.catalog_item_id, user.id)
    care_uuids = await _validate_care_products(db, body.care_product_ids, user.id)

    cycle_phase, cycle_day = await _cycle_snapshot(db, user.id, body.entry_date)

    entry = JournalEntry(
        user_id=user.id,
        entry_date=body.entry_date,
        status="completed",
        source="activity" if aid else "manual",
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    await _apply_entry_fields(
        entry,
        entry_date=body.entry_date,
        partner_id=body.partner_id,
        catalog_item_id=catalog_item.id if catalog_item else None,
        activity_type=catalog_item.name if catalog_item else body.activity_type or "",
        duration_minutes=body.duration_minutes,
        desire_before=body.desire_before,
        arousal_before=body.arousal_before,
        protection=protection,
        orgasms=body.orgasms,
        intensity=body.intensity,
        satisfaction=body.satisfaction,
        pleasure=body.pleasure,
        reactions=body.reactions,
        emotional_state=body.emotional_state,
        aftercare=body.aftercare or "",
        recovery=body.recovery,
        notes=body.notes or "",
        activity_log_id=aid,
        care_product_ids=care_uuids,
    )
    db.add(entry)
    await db.flush()
    return _entry_json(entry)


class CompleteBody(BaseModel):
    catalog_item_id: uuid.UUID | None = None
    activity_type: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    desire_before: int | None = Field(default=None, ge=1, le=5)
    arousal_before: int | None = Field(default=None, ge=1, le=5)
    protection: str = "none"
    orgasms: int | None = Field(default=None, ge=0, le=100)
    intensity: int | None = Field(default=None, ge=1, le=5)
    satisfaction: int | None = Field(default=None, ge=1, le=5)
    pleasure: int | None = Field(default=None, ge=1, le=5)
    reactions: list[str] | None = None
    emotional_state: list[str] | None = None
    aftercare: str | None = None
    recovery: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    care_product_ids: list[uuid.UUID] | None = None


@json_router.post("/entries/{entry_id}/complete")
async def json_complete_entry(
    entry_id: uuid.UUID,
    body: CompleteBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Заполнить детали draft-записи (JSON, для мобильного)."""
    entry = (
        await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user.id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Journal entry not found")
    if entry.status != "draft":
        raise HTTPException(400, "Only draft entries can be completed")

    protection = body.protection if body.protection in PROTECTION_TYPES else "none"
    catalog_item = await _resolve_catalog_item(db, body.catalog_item_id, user.id)
    care_uuids = await _validate_care_products(db, body.care_product_ids, user.id)
    await _apply_entry_fields(
        entry,
        entry_date=entry.entry_date,
        partner_id=entry.partner_id,
        catalog_item_id=catalog_item.id if catalog_item else None,
        activity_type=catalog_item.name if catalog_item else body.activity_type or "",
        duration_minutes=body.duration_minutes,
        desire_before=body.desire_before,
        arousal_before=body.arousal_before,
        protection=protection,
        orgasms=body.orgasms,
        intensity=body.intensity,
        satisfaction=body.satisfaction,
        pleasure=body.pleasure,
        reactions=body.reactions,
        emotional_state=body.emotional_state,
        aftercare=body.aftercare or "",
        recovery=body.recovery,
        notes=body.notes or "",
        activity_log_id=entry.activity_log_id,
        care_product_ids=care_uuids,
    )
    await db.flush()
    return _entry_json(entry)


class PartnerBody(BaseModel):
    name: str
    notes: str | None = None


@json_router.post("/partners", status_code=201)
async def json_add_partner(
    body: PartnerBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip()[:100]
    if not name:
        raise HTTPException(400, "Name is required")
    partner = JournalPartner(user_id=user.id, name=name, notes=(body.notes or "").strip() or None)
    db.add(partner)
    await db.flush()
    return {
        "id": str(partner.id),
        "name": partner.name,
        "notes": partner.notes,
    }


@json_router.delete("/entries/{entry_id}", status_code=204)
async def json_delete_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить запись журнала — для мобильного клиента (owner-scoped)."""
    entry = (
        await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user.id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Journal entry not found")
    await db.delete(entry)
    await db.flush()
    return None


@json_router.delete("/partners/{partner_id}", status_code=204)
async def json_delete_partner(
    partner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить псевдоним партнёра — записи сохраняются, ссылка обнуляется (SET NULL)."""
    partner = (
        await db.execute(
            select(JournalPartner).where(JournalPartner.id == partner_id, JournalPartner.user_id == user.id)
        )
    ).scalar_one_or_none()
    if partner is None:
        raise HTTPException(404, "Partner not found")
    entries = (
        (
            await db.execute(
                select(JournalEntry).where(JournalEntry.user_id == user.id, JournalEntry.partner_id == partner_id)
            )
        )
        .scalars()
        .all()
    )
    for e in entries:
        e.partner_id = None
    await db.delete(partner)
    await db.flush()
    return None
