"""Sexual Journal API (M3 Personal Suite, Шаг 14, ROADMAP §7 4A).

Приватная запись фактической сексуальной жизни (PRODUCT_OVERVIEW §7) —
**relief-only** (PD-013): никакой игровой интеграции, никаких штрафов.
Все записи — Private Record (DATA_LIFECYCLE.md): отдельное удаление,
связи с Timer/Health — по ID без раскрытия (мягкие ссылки, без FK).

Страницы:
- GET  /journal                     — записи журнала + псевдонимы партнёров
- POST /journal/entries             — создать запись (снимок фазы Cycle)
- POST /journal/entries/{id}/delete — удалить запись
- POST /journal/partners            — создать псевдоним партнёра
- POST /journal/partners/{id}/delete — удалить псевдоним

JSON API (мобильный/bearer):
- GET  /api/v2/journal              — сводка + записи + партнёры
- POST /api/v2/journal/entries      — создать запись
- POST /api/v2/journal/partners     — создать псевдоним
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.journal import PROTECTION_TYPES, REACTION_CHOICES, SCALE_1_5, JournalEntry, JournalPartner
from app.models.user import User
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
    satisfactions = [r.satisfaction for r in rows if r.satisfaction is not None]
    last = rows[0] if rows else None
    return {
        "count_30d": len(rows),
        "total": total,
        "last_date": last.entry_date.isoformat() if last else None,
        "last_type": last.activity_type if last else None,
        "avg_satisfaction": round(sum(satisfactions) / len(satisfactions), 1) if satisfactions else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────


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
            "entries": [
                {
                    "id": str(e.id),
                    "entry_date": e.entry_date.isoformat(),
                    "partner_id": str(e.partner_id) if e.partner_id else None,
                    "partner_name": partner_names.get(str(e.partner_id)) if e.partner_id else None,
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
                    "cycle_phase": e.cycle_phase,
                    "cycle_day": e.cycle_day,
                }
                for e in entries
            ],
            "partners": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "notes": p.notes,
                    "entries_count": sum(1 for e in entries if e.partner_id == p.id),
                }
                for p in partners
            ],
            "scales": list(SCALE_1_5),
            "protection_types": list(PROTECTION_TYPES),
            "reaction_choices": list(REACTION_CHOICES),
        },
    )


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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        d = date.fromisoformat(entry_date.strip())
    except ValueError:
        raise HTTPException(400, "Invalid entry_date (ISO 8601)") from None

    partner_uuid = None
    if partner_id.strip():
        try:
            partner_uuid = uuid.UUID(partner_id.strip())
        except ValueError:
            raise HTTPException(400, "Invalid partner_id") from None
        # псевдоним должен принадлежать пользователю (object-level auth)
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

    cycle_phase, cycle_day = await _cycle_snapshot(db, user.id, d)

    entry = JournalEntry(
        user_id=user.id,
        entry_date=d,
        partner_id=partner_uuid,
        activity_type=(activity_type or "").strip()[:100] or None,
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
        aftercare=(aftercare or "").strip() or None,
        recovery=_parse_scale(recovery, "recovery"),
        notes=(notes or "").strip() or None,
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    db.add(entry)
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
        "cycle_phase": e.cycle_phase,
        "cycle_day": e.cycle_day,
    }


class EntryBody(BaseModel):
    entry_date: date
    partner_id: uuid.UUID | None = None
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

    cycle_phase, cycle_day = await _cycle_snapshot(db, user.id, body.entry_date)

    entry = JournalEntry(
        user_id=user.id,
        entry_date=body.entry_date,
        partner_id=body.partner_id,
        activity_type=(body.activity_type or "").strip()[:100] or None,
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
        aftercare=(body.aftercare or "").strip() or None,
        recovery=body.recovery,
        notes=(body.notes or "").strip() or None,
        cycle_phase=cycle_phase,
        cycle_day=cycle_day,
    )
    db.add(entry)
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
