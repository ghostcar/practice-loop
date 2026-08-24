"""Health + Cycle — Business Logic Service Layer.

Extracted from app/api/health.py (ADR-163) to keep routers thin:
all CRUD, validation, serialization, and domain queries live here.

Public API:
  - cycle_phase / day_of_cycle   — cycle calculation helpers (reused by care, journal, insights)
  - get_health_page_context      — template context for GET /health
  - health_summary               — dashboard summary
  - get_cycle_context            — cycle settings + events + phase
  - save_health_state / add_lab / delete_lab
  - save_cycle_settings / add_cycle_event / delete_cycle_event
  - analyze_labs_async           — LLM analysis
  - get_body_cycle_page_context / log_body_cycle
  - json_* variants for mobile API
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import (
    CONTRACEPTION_TYPES,
    CYCLE_EVENT_TYPES,
    SCALE_1_5,
    CycleEvent,
    CycleSettings,
    HealthState,
    LabRecord,
)
from app.services.errors import NotFoundError
from app.timeutils import local_today

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cycle phase helpers
# ─────────────────────────────────────────────────────────────────────────────

CYCLE_PHASES = ("menstrual", "follicular", "ovulation", "luteal")


def cycle_phase(day_of_cycle: int, cycle_length: int, period_length: int) -> str:
    """Estimated phase by day of cycle. Never presented as fact."""
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


def day_of_cycle(events: list[CycleEvent], settings: CycleSettings | None, today: date) -> int | None:
    """Day of cycle from last bleeding start (first day after gap >= 3 days).

    Returns None if no bleeding data.
    """
    bleeds = sorted(
        (e for e in events if e.event_type == "bleeding"),
        key=lambda e: e.event_date,
    )
    if not bleeds:
        return None
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


def parse_analysis_param(raw: str) -> dict | None:
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


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard summary (relief-only, informational)
# ─────────────────────────────────────────────────────────────────────────────


async def health_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Brief summary for dashboard: today's check-in, lab count, cycle phase."""
    today = local_today()
    state = (
        await db.execute(select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == today))
    ).scalar_one_or_none()
    labs_count = (await db.execute(select(func.count(LabRecord.id)).where(LabRecord.user_id == user_id))).scalar() or 0
    cycle = await get_cycle_context(db, user_id)
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
# Cycle context builder (shared for page + JSON)
# ─────────────────────────────────────────────────────────────────────────────


async def get_cycle_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    settings = (await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))).scalar_one_or_none()
    events = (await db.execute(select(CycleEvent).where(CycleEvent.user_id == user_id))).scalars().all()
    today = local_today()
    doc = day_of_cycle(list(events), settings, today)
    ph = None
    if doc is not None:
        ph = cycle_phase(
            doc,
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
        "phase": ph,
        "day_of_cycle": doc,
        "phase_estimated": ph is not None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page context builder
# ─────────────────────────────────────────────────────────────────────────────


async def get_health_page_context(
    db: AsyncSession,
    user,
    *,
    analysis: str = "",
    error: str = "",
) -> dict:
    """Build full template context for GET /health page."""
    from app.prefs import get_prefs

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
    ph = None
    doc = day_of_cycle(list(events), settings, today)
    if doc is not None:
        ph = cycle_phase(
            doc,
            settings.cycle_length if settings else 28,
            settings.period_length if settings else 5,
        )

    return {
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
        "cycle_phase": ph,
        "day_of_cycle": doc,
        "scales": list(SCALE_1_5),
        "contraception_types": list(CONTRACEPTION_TYPES),
        "cycle_event_types": list(CYCLE_EVENT_TYPES),
        "analysis": parse_analysis_param(analysis),
        "analysis_error": error,
        "llm_mode": get_prefs().llm_mode,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — HealthState
# ─────────────────────────────────────────────────────────────────────────────


async def save_health_state(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    event_date: str,
    mood: str,
    energy: str,
    sleep_hours: str,
    sleep_quality: str,
    recovery: str,
    skin_sensitivity: str,
    post_session_drop: str,
    hrt_taken: str,
    symptoms: str,
    notes: str,
) -> HealthState:
    try:
        d = date.fromisoformat(event_date.strip())
    except ValueError:
        raise ValueError("Invalid event_date (ISO 8601)") from None
    symptom_list = [x.strip() for x in symptoms.split(",") if x.strip()] if symptoms.strip() else None
    sleep = None
    if sleep_hours.strip():
        try:
            sleep = float(sleep_hours)
        except ValueError:
            raise ValueError("Invalid sleep_hours") from None
    row = (
        await db.execute(select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == d))
    ).scalar_one_or_none()
    if row is None:
        row = HealthState(user_id=user_id, event_date=d)
        db.add(row)
    row.mood = parse_scale(mood, "mood")
    row.energy = parse_scale(energy, "energy")
    row.sleep_hours = sleep
    row.sleep_quality = parse_scale(sleep_quality, "sleep_quality")
    row.recovery = parse_scale(recovery, "recovery")
    row.skin_sensitivity = parse_scale(skin_sensitivity, "skin_sensitivity")
    row.post_session_drop = post_session_drop.strip().lower() in {"1", "on", "true", "yes"}
    row.hrt_taken = hrt_taken.strip().lower() in {"1", "on", "true", "yes"}
    row.symptoms = symptom_list
    row.notes = (notes or "").strip() or None
    await db.flush()
    return row


def state_dict(s: HealthState) -> dict:
    return {
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


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — LabRecord
# ─────────────────────────────────────────────────────────────────────────────


async def add_lab(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    measured_at: str,
    value: str,
    unit: str,
    ref_range: str,
    lab_name: str,
    flagged: str,
    notes: str,
) -> LabRecord:
    try:
        val = float(value)
        mdate = date.fromisoformat(measured_at.strip())
    except ValueError:
        raise ValueError("Invalid value or measured_at") from None
    rmin = None
    rmax = None
    if ref_range.strip():
        parts = [p.strip() for p in ref_range.replace("–", "-").split("-") if p.strip()]
        if len(parts) == 2:
            try:
                rmin = float(parts[0])
                rmax = float(parts[1])
            except ValueError:
                pass
    rec = LabRecord(
        user_id=user_id,
        name=name.strip()[:200],
        measured_at=mdate,
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
    return rec


async def delete_lab(db: AsyncSession, user_id: uuid.UUID, lab_id: uuid.UUID) -> None:
    rec = (
        await db.execute(select(LabRecord).where(LabRecord.id == lab_id, LabRecord.user_id == user_id))
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError("Lab record not found")
    await db.delete(rec)
    await db.flush()


def lab_dict(rec: LabRecord) -> dict:
    return {
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


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — CycleSettings / CycleEvent
# ─────────────────────────────────────────────────────────────────────────────


async def save_cycle_settings(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    cycle_length: str,
    period_length: str,
    contraception: str,
    notes: str,
) -> CycleSettings:
    try:
        cl = int(cycle_length)
        pl = int(period_length)
    except ValueError:
        raise ValueError("Invalid cycle lengths") from None
    if cl < 1 or cl > 120 or pl < 1 or pl > 30:
        raise ValueError("Cycle lengths out of range")
    if contraception not in CONTRACEPTION_TYPES:
        contraception = "none"
    row = (await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))).scalar_one_or_none()
    if row is None:
        row = CycleSettings(user_id=user_id)
        db.add(row)
    row.cycle_length = cl
    row.period_length = pl
    row.contraception = contraception
    row.notes = (notes or "").strip() or None
    await db.flush()
    return row


async def add_cycle_event(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    event_date: str,
    event_type: str,
    value: str,
    notes: str,
) -> CycleEvent:
    try:
        d = date.fromisoformat(event_date.strip())
    except ValueError:
        raise ValueError("Invalid event_date (ISO 8601)") from None
    if event_type not in CYCLE_EVENT_TYPES:
        raise ValueError("Invalid event_type")
    ev = CycleEvent(
        user_id=user_id,
        event_date=d,
        event_type=event_type,
        value=(value or "").strip()[:50] or None,
        notes=(notes or "").strip() or None,
    )
    db.add(ev)
    await db.flush()
    return ev


async def delete_cycle_event(db: AsyncSession, user_id: uuid.UUID, event_id: uuid.UUID) -> None:
    ev = (
        await db.execute(select(CycleEvent).where(CycleEvent.id == event_id, CycleEvent.user_id == user_id))
    ).scalar_one_or_none()
    if ev is None:
        raise NotFoundError("Cycle event not found")
    await db.delete(ev)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# LLM Analysis (ADR-087)
# ─────────────────────────────────────────────────────────────────────────────


async def analyze_labs_async(db, user_id, llm_config, *, locale: str, llm_mode: str) -> dict:
    from app.llm.pipeline import analyze_labs

    return await analyze_labs(db, user_id, llm_config, locale=locale, llm_mode=llm_mode)


# ─────────────────────────────────────────────────────────────────────────────
# Body Cycle page (Step 13b)
# ─────────────────────────────────────────────────────────────────────────────


async def get_body_cycle_page_context(db: AsyncSession, user) -> list:
    from app.models.body_cycle import BodyCycleLog

    logs = (
        (
            await db.execute(
                select(BodyCycleLog)
                .where(BodyCycleLog.user_id == user.id)
                .order_by(BodyCycleLog.logged_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return logs


async def log_body_cycle(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    cycle_phase: str,
    energy_level: int,
    soreness_level: int,
    notes: str,
) -> None:
    from app.models.body_cycle import BodyCycleLog

    log_entry = BodyCycleLog(
        user_id=user_id,
        cycle_phase=cycle_phase,
        energy_level=energy_level,
        soreness_level=soreness_level,
        notes=notes,
    )
    db.add(log_entry)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — queries
# ─────────────────────────────────────────────────────────────────────────────


async def json_health_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    today = local_today()
    state = (
        await db.execute(select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == today))
    ).scalar_one_or_none()
    labs = (
        (await db.execute(select(LabRecord).where(LabRecord.user_id == user_id).order_by(LabRecord.measured_at.desc())))
        .scalars()
        .all()
    )
    cycle = await get_cycle_context(db, user_id)
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
        "labs": [lab_dict(rec) for rec in labs[:20]],
    }


async def json_list_states(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    states = (
        (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user_id).order_by(HealthState.event_date.desc())
            )
        )
        .scalars()
        .all()
    )
    return [state_dict(s) for s in states]


async def json_list_labs(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    labs = (
        (await db.execute(select(LabRecord).where(LabRecord.user_id == user_id).order_by(LabRecord.measured_at.desc())))
        .scalars()
        .all()
    )
    return [lab_dict(rec) for rec in labs]


async def json_cycle(db: AsyncSession, user_id: uuid.UUID) -> dict:
    return await get_cycle_context(db, user_id)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — CRUD
# ─────────────────────────────────────────────────────────────────────────────


class StateBody(BaseModel):
    event_date: date
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    sleep_hours: float | None = None
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    recovery: int | None = Field(default=None, ge=1, le=5)
    symptoms: list[str] | None = None
    notes: str | None = None


async def json_save_state(db: AsyncSession, user_id: uuid.UUID, body: StateBody) -> dict:
    row = (
        await db.execute(
            select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == body.event_date)
        )
    ).scalar_one_or_none()
    if row is None:
        row = HealthState(user_id=user_id, event_date=body.event_date)
        db.add(row)
    row.mood = body.mood
    row.energy = body.energy
    row.sleep_hours = body.sleep_hours
    row.sleep_quality = body.sleep_quality
    row.recovery = body.recovery
    row.symptoms = body.symptoms
    row.notes = (body.notes or "").strip() or None
    await db.flush()
    return state_dict(row)


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


async def json_add_lab(db: AsyncSession, user_id: uuid.UUID, body: LabBody) -> dict:
    if not body.name.strip():
        raise ValueError("Name is required")
    rec = LabRecord(
        user_id=user_id,
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
    return lab_dict(rec)


async def json_delete_lab(db: AsyncSession, user_id: uuid.UUID, lab_id: uuid.UUID) -> None:
    await delete_lab(db, user_id, lab_id)


class CycleEventBody(BaseModel):
    event_date: date
    event_type: str
    value: str | None = None
    notes: str | None = None


async def json_add_cycle_event(db: AsyncSession, user_id: uuid.UUID, body: CycleEventBody) -> dict:
    if body.event_type not in CYCLE_EVENT_TYPES:
        raise ValueError("Invalid event_type")
    ev = CycleEvent(
        user_id=user_id,
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


async def json_delete_cycle_event(db: AsyncSession, user_id: uuid.UUID, event_id: uuid.UUID) -> None:
    await delete_cycle_event(db, user_id, event_id)


class CycleSettingsBody(BaseModel):
    cycle_length: int = Field(default=28, ge=1, le=120)
    period_length: int = Field(default=5, ge=1, le=30)
    contraception: str = "none"
    notes: str | None = None


async def json_save_cycle_settings(db: AsyncSession, user_id: uuid.UUID, body: CycleSettingsBody) -> dict:
    contraception = body.contraception if body.contraception in CONTRACEPTION_TYPES else "none"
    row = (await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))).scalar_one_or_none()
    if row is None:
        row = CycleSettings(user_id=user_id)
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
