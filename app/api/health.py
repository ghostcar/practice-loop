"""Health + Cycle foundation API (M3 Personal Suite, Шаг 13, ROADMAP §7 4D).

Health-модуль — **relief-only** (PD-013): никакой игровой интеграции, никаких
штрафов. Все записи Private Record (DATA_LIFECYCLE.md). Сигналы Health могут
только открыть окно/смягчить/поставить на паузу/остановить — но в этом модуле
никаких сигналов наружу нет (адаптеры — в Tracker/Timer).

Страницы:
- GET  /health                    — check-in сегодня + timeline + лабораторные + Cycle
- POST /health/state              — создать/обновить check-in на дату
- POST /health/labs               — добавить лабораторную запись
- POST /health/labs/{id}/delete   — удалить запись
- POST /health/cycle/settings     — обновить настройки Cycle
- POST /health/cycle/events       — добавить событие Cycle
- POST /health/cycle/events/{id}/delete — удалить событие
- POST /health/analyze            — LLM-разбор анализов (ADR-087, режим из prefs)

JSON API (мобильный/bearer):
- GET  /api/v2/health             — сводка: последний check-in + cycle + labs
- GET  /api/v2/health/states      — timeline check-in'ов
- GET  /api/v2/health/labs        — лабораторные записи
- GET  /api/v2/health/cycle       — настройки + события + расчётная фаза
- POST /api/v2/health/state       — записать check-in
- POST /api/v2/health/labs        — добавить лабораторную запись
- POST /api/v2/health/cycle/events — добавить событие Cycle
- POST /api/v2/health/analyze     — LLM-разбор анализов (JSON, режим из prefs)
"""

from __future__ import annotations

import json
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
from app.llm.pipeline import analyze_labs, get_active_llm_config
from app.models.health import (
    CONTRACEPTION_TYPES,
    CYCLE_EVENT_TYPES,
    SCALE_1_5,
    CycleEvent,
    CycleSettings,
    HealthState,
    LabRecord,
)
from app.models.user import User
from app.prefs import get_prefs
from app.templates_setup import templates
from app.timeutils import local_today

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# ─────────────────────────────────────────────────────────────────────────────
# Cycle phase helpers
# ─────────────────────────────────────────────────────────────────────────────

# Фазы по дню цикла (при cycle_length=28): 1..period_length — menstruation,
# далее follicular, ~14 — ovulation, далее luteal.
CYCLE_PHASES = ("menstrual", "follicular", "ovulation", "luteal")


def _cycle_phase(day_of_cycle: int, cycle_length: int, period_length: int) -> str:
    """Расчётная фаза по дню цикла. Никогда не выдаётся за факт."""
    if day_of_cycle <= period_length:
        return "menstrual"
    if cycle_length <= 0:
        return "follicular"
    ovulation_day = max(period_length + 1, cycle_length // 2)
    if day_of_cycle == ovulation_day:
        return "ovulation"
    if day_of_cycle < ovulation_day:
        return "follicular"
    return "luteal"


def _day_of_cycle(events: list[CycleEvent], settings: CycleSettings | None, today: date) -> int | None:
    """День цикла от последнего начала кровотечения (первый день после перерыва ≥3 дней).

    Возвращает None, если данных о начале цикла нет.
    """
    bleeds = sorted(
        (e for e in events if e.event_type == "bleeding"),
        key=lambda e: e.event_date,
    )
    if not bleeds:
        return None
    # начало последнего цикла: первый день кровотечения после перерыва ≥3 дней
    start = None
    prev = None
    for e in bleeds:
        if prev is None or (e.event_date - prev.event_date).days >= 3:
            start = e.event_date
        prev = e
    if start is None:
        return None
    cycle_length = (settings.cycle_length if settings and settings.cycle_length else 28) or 28
    delta = (today - start).days
    return (delta % cycle_length) + 1


# ─────────────────────────────────────────────────────────────────────────────
# LLM analysis param parsing (ADR-087)
# ─────────────────────────────────────────────────────────────────────────────


def _parse_analysis_param(raw: str) -> dict | None:
    """Parse the ``?analysis=...`` JSON query param into a safe dict."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return {
        "summary": str(parsed.get("summary") or "")[:2000],
        "observations": [str(i)[:500] for i in parsed.get("observations", []) if isinstance(i, str)][:20],
        "assumptions": [str(i)[:500] for i in parsed.get("assumptions", []) if isinstance(i, str)][:20],
        "questions_for_doctor": [str(i)[:500] for i in parsed.get("questions_for_doctor", []) if isinstance(i, str)][
            :20
        ],
        "recommendations": [str(i)[:500] for i in parsed.get("recommendations", []) if isinstance(i, str)][:20],
        "mode": str(parsed.get("_mode") or "safe"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard summary (relief-only, informational)
# ─────────────────────────────────────────────────────────────────────────────


async def _health_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Краткая сводка для дашборда: check-in сегодня, число анализов, фаза цикла."""
    today = local_today()
    state = (
        await db.execute(select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == today))
    ).scalar_one_or_none()
    labs_count = (await db.execute(select(func.count(LabRecord.id)).where(LabRecord.user_id == user_id))).scalar() or 0
    cycle = await _get_cycle_context(db, user_id)
    return {
        "today": today.isoformat(),
        "has_checkin": state is not None,
        "mood": state.mood if state else None,
        "energy": state.energy if state else None,
        "sleep_hours": state.sleep_hours if state else None,
        "symptoms": (state.symptoms or []) if state else [],
        "labs_count": labs_count,
        "phase": cycle.get("phase"),
        "day_of_cycle": cycle.get("day_of_cycle"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health", response_class=HTMLResponse)
async def health_page(
    request: Request,
    analysis: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    today = local_today()
    states = (
        (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user.id).order_by(HealthState.event_date.desc())
            )
        )
        .scalars()
        .all()
    )
    labs = (
        (await db.execute(select(LabRecord).where(LabRecord.user_id == user.id).order_by(LabRecord.measured_at.desc())))
        .scalars()
        .all()
    )
    settings = (await db.execute(select(CycleSettings).where(CycleSettings.user_id == user.id))).scalar_one_or_none()
    events = (
        (
            await db.execute(
                select(CycleEvent).where(CycleEvent.user_id == user.id).order_by(CycleEvent.event_date.desc())
            )
        )
        .scalars()
        .all()
    )

    today_state = next((s for s in states if s.event_date == today), None)
    phase = None
    day_of_cycle = _day_of_cycle(list(events), settings, today)
    if day_of_cycle is not None:
        phase = _cycle_phase(
            day_of_cycle,
            settings.cycle_length if settings else 28,
            settings.period_length if settings else 5,
        )

    return templates.TemplateResponse(
        request=request,
        name="health.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "today": today,
            "today_state": today_state,
            "states": [
                {
                    "id": str(s.id),
                    "event_date": s.event_date.isoformat(),
                    "mood": s.mood,
                    "energy": s.energy,
                    "sleep_hours": s.sleep_hours,
                    "sleep_quality": s.sleep_quality,
                    "recovery": s.recovery,
                    "symptoms": s.symptoms or [],
                    "notes": s.notes,
                }
                for s in states
            ],
            "labs": [
                {
                    "id": str(rec.id),
                    "name": rec.name,
                    "measured_at": rec.measured_at.isoformat(),
                    "value": rec.value,
                    "unit": rec.unit,
                    "ref_min": rec.ref_min,
                    "ref_max": rec.ref_max,
                    "lab_name": rec.lab_name,
                    "flagged": rec.flagged,
                    "notes": rec.notes,
                    "out_of_range": (rec.ref_min is not None and rec.value < rec.ref_min)
                    or (rec.ref_max is not None and rec.value > rec.ref_max),
                }
                for rec in labs
            ],
            "cycle_settings": (
                {
                    "cycle_length": settings.cycle_length,
                    "period_length": settings.period_length,
                    "contraception": settings.contraception,
                    "notes": settings.notes,
                }
                if settings
                else None
            ),
            "cycle_events": [
                {
                    "id": str(e.id),
                    "event_date": e.event_date.isoformat(),
                    "event_type": e.event_type,
                    "value": e.value,
                    "notes": e.notes,
                }
                for e in events
            ],
            "cycle_phase": phase,
            "day_of_cycle": day_of_cycle,
            "scales": list(SCALE_1_5),
            "contraception_types": list(CONTRACEPTION_TYPES),
            "cycle_event_types": list(CYCLE_EVENT_TYPES),
            # LLM lab analysis result (ADR-087) — passed via query param from
            # the POST /health/analyze redirect (stateless, not persisted).
            "analysis": _parse_analysis_param(analysis),
            "analysis_error": error,
            "llm_mode": get_prefs().llm_mode,
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


@router.post("/health/state")
async def save_state(
    request: Request,
    event_date: str = Form(...),
    mood: str = Form(default=""),
    energy: str = Form(default=""),
    sleep_hours: str = Form(default=""),
    sleep_quality: str = Form(default=""),
    recovery: str = Form(default=""),
    symptoms: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        d = date.fromisoformat(event_date.strip())
    except ValueError:
        raise HTTPException(400, "Invalid event_date (ISO 8601)") from None
    symptom_list = [x.strip() for x in symptoms.split(",") if x.strip()] if symptoms.strip() else None
    sleep = None
    if sleep_hours.strip():
        try:
            sleep = float(sleep_hours)
        except ValueError:
            raise HTTPException(400, "Invalid sleep_hours") from None
    row = (
        await db.execute(select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == d))
    ).scalar_one_or_none()
    if row is None:
        row = HealthState(user_id=user.id, event_date=d)
        db.add(row)
    row.mood = _parse_scale(mood, "mood")
    row.energy = _parse_scale(energy, "energy")
    row.sleep_hours = sleep
    row.sleep_quality = _parse_scale(sleep_quality, "sleep_quality")
    row.recovery = _parse_scale(recovery, "recovery")
    row.symptoms = symptom_list
    row.notes = (notes or "").strip() or None
    await db.flush()
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/analyze")
async def analyze_labs_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run LLM analysis of lab results (ADR-087). Form POST → redirect with result.

    Mode comes from the user preference ``llm_mode`` (safe | expanded); without
    an active LLM config we redirect with an error flash instead of failing.
    """
    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        return RedirectResponse(url="/health?error=no_llm_config", status_code=303)
    locale = detect_locale(request, user.locale)
    mode = get_prefs().llm_mode
    try:
        result = await analyze_labs(db, user.id, llm_config, locale=locale, llm_mode=mode)
    except Exception as exc:  # LLM/parse failures — surface a retry, don't crash
        logger.warning("health analyze failed: %s", exc)
        return RedirectResponse(url="/health?error=analyze_failed", status_code=303)
    import json as _json

    encoded = _json.dumps(result, ensure_ascii=False)
    return RedirectResponse(url=f"/health?analysis={encoded}", status_code=303)


@router.post("/health/labs")
async def add_lab(
    request: Request,
    name: str = Form(...),
    measured_at: str = Form(...),
    value: str = Form(...),
    unit: str = Form(default=""),
    ref_range: str = Form(default=""),
    lab_name: str = Form(default=""),
    flagged: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    try:
        d = date.fromisoformat(measured_at.strip())
        val = float(value)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid measured_at or value") from None
    rmin = rmax = None
    if ref_range.strip():
        # accept "120 – 160", "120-160", "120 160"
        parts = [p for p in ref_range.replace("–", "-").replace("−", "-").split("-") if p.strip()]
        try:
            if len(parts) == 1:
                rmin = float(parts[0])
            elif len(parts) == 2:
                rmin = float(parts[0])
                rmax = float(parts[1])
        except ValueError:
            raise HTTPException(400, "Invalid reference range") from None
    rec = LabRecord(
        user_id=user.id,
        name=name,
        measured_at=d,
        value=val,
        unit=(unit or "").strip()[:50] or None,
        ref_min=rmin,
        ref_max=rmax,
        lab_name=(lab_name or "").strip()[:200] or None,
        flagged=flagged.strip().lower() in {"1", "on", "true", "yes"},
        notes=(notes or "").strip() or None,
    )
    db.add(rec)
    await db.flush()
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/labs/{lab_id}/delete")
async def delete_lab(
    request: Request,
    lab_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = (
        await db.execute(select(LabRecord).where(LabRecord.id == lab_id, LabRecord.user_id == user.id))
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(404, "Lab record not found")
    await db.delete(rec)
    await db.flush()
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/cycle/settings")
async def save_cycle_settings(
    request: Request,
    cycle_length: str = Form(default="28"),
    period_length: str = Form(default="5"),
    contraception: str = Form(default="none"),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        cl = int(cycle_length)
        pl = int(period_length)
    except ValueError:
        raise HTTPException(400, "Invalid cycle lengths") from None
    if cl < 1 or cl > 120 or pl < 1 or pl > 30:
        raise HTTPException(400, "Cycle lengths out of range")
    if contraception not in CONTRACEPTION_TYPES:
        contraception = "none"
    row = (await db.execute(select(CycleSettings).where(CycleSettings.user_id == user.id))).scalar_one_or_none()
    if row is None:
        row = CycleSettings(user_id=user.id)
        db.add(row)
    row.cycle_length = cl
    row.period_length = pl
    row.contraception = contraception
    row.notes = (notes or "").strip() or None
    await db.flush()
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/cycle/events")
async def add_cycle_event(
    request: Request,
    event_date: str = Form(...),
    event_type: str = Form(...),
    value: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        d = date.fromisoformat(event_date.strip())
    except ValueError:
        raise HTTPException(400, "Invalid event_date (ISO 8601)") from None
    if event_type not in CYCLE_EVENT_TYPES:
        raise HTTPException(400, "Invalid event_type")
    ev = CycleEvent(
        user_id=user.id,
        event_date=d,
        event_type=event_type,
        value=(value or "").strip()[:50] or None,
        notes=(notes or "").strip() or None,
    )
    db.add(ev)
    await db.flush()
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/cycle/events/{event_id}/delete")
async def delete_cycle_event(
    request: Request,
    event_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = (
        await db.execute(select(CycleEvent).where(CycleEvent.id == event_id, CycleEvent.user_id == user.id))
    ).scalar_one_or_none()
    if ev is None:
        raise HTTPException(404, "Cycle event not found")
    await db.delete(ev)
    await db.flush()
    return RedirectResponse(url="/health", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────

json_router = APIRouter(prefix="/api/v2/health", tags=["health"])


async def _get_cycle_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    settings = (await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))).scalar_one_or_none()
    events = (await db.execute(select(CycleEvent).where(CycleEvent.user_id == user_id))).scalars().all()
    today = local_today()
    day_of_cycle = _day_of_cycle(list(events), settings, today)
    phase = None
    if day_of_cycle is not None:
        phase = _cycle_phase(
            day_of_cycle,
            settings.cycle_length if settings else 28,
            settings.period_length if settings else 5,
        )
    return {
        "settings": (
            {
                "cycle_length": settings.cycle_length,
                "period_length": settings.period_length,
                "contraception": settings.contraception,
            }
            if settings
            else None
        ),
        "events": [
            {
                "id": str(e.id),
                "event_date": e.event_date.isoformat(),
                "event_type": e.event_type,
                "value": e.value,
                "notes": e.notes,
            }
            for e in events
        ],
        "phase": phase,
        "day_of_cycle": day_of_cycle,
        "phase_estimated": phase is not None,
    }


@json_router.get("")
async def json_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = local_today()
    state = (
        await db.execute(select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today))
    ).scalar_one_or_none()
    labs = (
        (await db.execute(select(LabRecord).where(LabRecord.user_id == user.id).order_by(LabRecord.measured_at.desc())))
        .scalars()
        .all()
    )
    cycle = await _get_cycle_context(db, user.id)
    return {
        "today": today.isoformat(),
        "today_state": (
            {
                "mood": state.mood,
                "energy": state.energy,
                "sleep_hours": state.sleep_hours,
                "sleep_quality": state.sleep_quality,
                "recovery": state.recovery,
                "symptoms": state.symptoms or [],
                "notes": state.notes,
            }
            if state
            else None
        ),
        "cycle": cycle,
        "labs": [
            {
                "id": str(rec.id),
                "name": rec.name,
                "measured_at": rec.measured_at.isoformat(),
                "value": rec.value,
                "unit": rec.unit,
                "ref_min": rec.ref_min,
                "ref_max": rec.ref_max,
                "lab_name": rec.lab_name,
                "flagged": rec.flagged,
                "notes": rec.notes,
            }
            for rec in labs[:20]
        ],
    }


@json_router.get("/states")
async def json_states(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    states = (
        (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user.id).order_by(HealthState.event_date.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(s.id),
            "event_date": s.event_date.isoformat(),
            "mood": s.mood,
            "energy": s.energy,
            "sleep_hours": s.sleep_hours,
            "sleep_quality": s.sleep_quality,
            "recovery": s.recovery,
            "symptoms": s.symptoms or [],
            "notes": s.notes,
        }
        for s in states
    ]


@json_router.get("/labs")
async def json_labs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    labs = (
        (await db.execute(select(LabRecord).where(LabRecord.user_id == user.id).order_by(LabRecord.measured_at.desc())))
        .scalars()
        .all()
    )
    return [
        {
            "id": str(rec.id),
            "name": rec.name,
            "measured_at": rec.measured_at.isoformat(),
            "value": rec.value,
            "unit": rec.unit,
            "ref_min": rec.ref_min,
            "ref_max": rec.ref_max,
            "lab_name": rec.lab_name,
            "flagged": rec.flagged,
            "notes": rec.notes,
        }
        for rec in labs
    ]


@json_router.get("/cycle")
async def json_cycle(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _get_cycle_context(db, user.id)


class StateBody(BaseModel):
    event_date: date
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    sleep_hours: float | None = None
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    recovery: int | None = Field(default=None, ge=1, le=5)
    symptoms: list[str] | None = None
    notes: str | None = None


@json_router.post("/state", status_code=201)
async def json_save_state(
    body: StateBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        await db.execute(
            select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == body.event_date)
        )
    ).scalar_one_or_none()
    if row is None:
        row = HealthState(user_id=user.id, event_date=body.event_date)
        db.add(row)
    row.mood = body.mood
    row.energy = body.energy
    row.sleep_hours = body.sleep_hours
    row.sleep_quality = body.sleep_quality
    row.recovery = body.recovery
    row.symptoms = body.symptoms
    row.notes = (body.notes or "").strip() or None
    await db.flush()
    return {
        "id": str(row.id),
        "event_date": row.event_date.isoformat(),
        "mood": row.mood,
        "energy": row.energy,
        "sleep_hours": row.sleep_hours,
        "sleep_quality": row.sleep_quality,
        "recovery": row.recovery,
        "symptoms": row.symptoms or [],
        "notes": row.notes,
    }


class LabBody(BaseModel):
    name: str
    measured_at: date
    value: float
    unit: str | None = None
    ref_min: float | None = None
    ref_max: float | None = None
    lab_name: str | None = None
    flagged: bool = False
    notes: str | None = None


@json_router.post("/labs", status_code=201)
async def json_add_lab(
    body: LabBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not body.name.strip():
        raise HTTPException(400, "Name is required")
    rec = LabRecord(
        user_id=user.id,
        name=body.name.strip()[:200],
        measured_at=body.measured_at,
        value=body.value,
        unit=(body.unit or "").strip()[:50] or None,
        ref_min=body.ref_min,
        ref_max=body.ref_max,
        lab_name=(body.lab_name or "").strip()[:200] or None,
        flagged=body.flagged,
        notes=(body.notes or "").strip() or None,
    )
    db.add(rec)
    await db.flush()
    return {
        "id": str(rec.id),
        "name": rec.name,
        "measured_at": rec.measured_at.isoformat(),
        "value": rec.value,
        "unit": rec.unit,
        "ref_min": rec.ref_min,
        "ref_max": rec.ref_max,
        "flagged": rec.flagged,
    }


@json_router.delete("/labs/{lab_id}", status_code=204)
async def json_delete_lab(
    lab_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить лабораторную запись — для мобильного клиента (owner-scoped)."""
    rec = (
        await db.execute(select(LabRecord).where(LabRecord.id == lab_id, LabRecord.user_id == user.id))
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(404, "Lab record not found")
    await db.delete(rec)
    await db.flush()
    return None


class CycleEventBody(BaseModel):
    event_date: date
    event_type: str
    value: str | None = None
    notes: str | None = None


@json_router.post("/cycle/events", status_code=201)
async def json_add_cycle_event(
    body: CycleEventBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.event_type not in CYCLE_EVENT_TYPES:
        raise HTTPException(400, "Invalid event_type")
    ev = CycleEvent(
        user_id=user.id,
        event_date=body.event_date,
        event_type=body.event_type,
        value=(body.value or "").strip()[:50] or None,
        notes=(body.notes or "").strip() or None,
    )
    db.add(ev)
    await db.flush()
    return {
        "id": str(ev.id),
        "event_date": ev.event_date.isoformat(),
        "event_type": ev.event_type,
        "value": ev.value,
        "notes": ev.notes,
    }


@json_router.delete("/cycle/events/{event_id}", status_code=204)
async def json_delete_cycle_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить событие Cycle — для мобильного клиента (owner-scoped)."""
    ev = (
        await db.execute(select(CycleEvent).where(CycleEvent.id == event_id, CycleEvent.user_id == user.id))
    ).scalar_one_or_none()
    if ev is None:
        raise HTTPException(404, "Cycle event not found")
    await db.delete(ev)
    await db.flush()
    return None


class CycleSettingsBody(BaseModel):
    cycle_length: int = Field(default=28, ge=1, le=120)
    period_length: int = Field(default=5, ge=1, le=30)
    contraception: str = "none"
    notes: str | None = None


@json_router.post("/cycle/settings", status_code=201)
async def json_save_cycle_settings(
    body: CycleSettingsBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Обновить настройки Cycle (upsert) — для мобильного клиента."""
    contraception = body.contraception if body.contraception in CONTRACEPTION_TYPES else "none"
    row = (await db.execute(select(CycleSettings).where(CycleSettings.user_id == user.id))).scalar_one_or_none()
    if row is None:
        row = CycleSettings(user_id=user.id)
        db.add(row)
    row.cycle_length = body.cycle_length
    row.period_length = body.period_length
    row.contraception = contraception
    row.notes = (body.notes or "").strip() or None
    await db.flush()
    return {
        "cycle_length": row.cycle_length,
        "period_length": row.period_length,
        "contraception": row.contraception,
        "notes": row.notes,
    }


@json_router.post("/analyze")
async def json_analyze_labs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run LLM analysis of lab results (ADR-087). Mode from prefs.llm_mode."""
    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        raise HTTPException(400, "No active LLM config — configure one in /llm-configs")
    locale = detect_locale(request, user.locale)
    mode = get_prefs().llm_mode
    try:
        result = await analyze_labs(db, user.id, llm_config, locale=locale, llm_mode=mode)
    except Exception as exc:
        logger.warning("health analyze (json) failed: %s", exc)
        raise HTTPException(502, "LLM analysis failed — retry") from exc
    # strip internal usage/mode, keep it clean for mobile clients
    return {
        "summary": result.get("summary", ""),
        "observations": result.get("observations", []),
        "assumptions": result.get("assumptions", []),
        "questions_for_doctor": result.get("questions_for_doctor", []),
        "recommendations": result.get("recommendations", []),
        "mode": result.get("_mode", mode),
    }
