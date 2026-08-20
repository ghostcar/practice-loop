"""Personal Insights API (M3 Personal Suite, Шаг 17, ROADMAP §7 4E).

Явно запрошенный кросс-модульный LLM-анализ личных данных (PRODUCT_OVERVIEW §12):
тенденции и связи между активностями, таймером, журналом, состоянием, уходом,
тренировками и диетами. Пользователь выбирает разделы и период; анализ показывает
использованные данные и не объявляет корреляцию причиной. **Relief-only** (PD-013):
без игровой интеграции. Все записи Private Record.

Страницы:
- GET  /insights                     — пикер разделов/периода + результат + история
- POST /insights/run                 — запустить анализ (LLM)
- POST /insights/runs/{id}/delete    — удалить запуск

JSON API (мобильный/bearer):
- GET  /api/v2/insights              — история запусков
- POST /api/v2/insights              — запустить анализ
- GET  /api/v2/insights/runs/{id}    — результат конкретного запуска
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.pipeline import analyze_insights, get_active_llm_config
from app.llm.repair import JsonRepairError
from app.models.insights import INSIGHT_SECTIONS, InsightFinding, InsightRun
from app.models.user import User
from app.prefs import get_prefs
from app.templates_setup import templates
from app.timeutils import local_today

logger = logging.getLogger(__name__)

router = APIRouter(tags=["insights"])
json_router = APIRouter(prefix="/api/v2/insights", tags=["insights"])

DEFAULT_DAYS = 30


def _default_period() -> tuple[date, date]:
    end = local_today()
    start = end - timedelta(days=DEFAULT_DAYS)
    return start, end


def _parse_period(start_raw: str, end_raw: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_raw.strip())
    except ValueError:
        raise HTTPException(400, "Invalid period_start (ISO 8601)") from None
    try:
        end = date.fromisoformat(end_raw.strip())
    except ValueError:
        raise HTTPException(400, "Invalid period_end (ISO 8601)") from None
    if end < start:
        start, end = end, start
    return start, end


def _run_view(run: InsightRun) -> dict:
    return {
        "id": str(run.id),
        "period_start": run.period_start.isoformat(),
        "period_end": run.period_end.isoformat(),
        "sections": run.sections or list(INSIGHT_SECTIONS),
        "status": run.status,
        "summary": run.summary,
        "usage_tokens": run.usage_tokens,
        "usage_cost": run.usage_cost,
        "error": run.error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "findings": [_finding_view(f) for f in run.findings],
    }


def _finding_view(f: InsightFinding) -> dict:
    return {
        "id": str(f.id),
        "section": f.section,
        "title": f.title,
        "summary": f.summary,
        "used_data": f.used_data or [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard summary (relief-only, informational)
# ─────────────────────────────────────────────────────────────────────────────


async def _insights_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Краткая сводка для дашборда: последний запуск + число находок."""
    run = (
        (
            await db.execute(
                select(InsightRun).where(InsightRun.user_id == user_id).order_by(InsightRun.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if run is None:
        return {"has_runs": False, "runs_count": 0}
    count = (await db.execute(select(func.count(InsightRun.id)).where(InsightRun.user_id == user_id))).scalar() or 0
    return {
        "has_runs": True,
        "runs_count": count,
        "last_date": run.created_at.date().isoformat() if run.created_at else None,
        "last_status": run.status,
        "last_summary": run.summary,
        "findings_count": len(run.findings),
        "period": f"{run.period_start.isoformat()} — {run.period_end.isoformat()}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(
    request: Request,
    run_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    runs = (
        (
            await db.execute(
                select(InsightRun).where(InsightRun.user_id == user.id).order_by(InsightRun.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    selected = None
    if run_id is not None:
        selected = next((r for r in runs if r.id == run_id), None)
        if selected is None:
            # чужой или несуществующий — 404
            raise HTTPException(404, "Insight run not found")
    if selected is None and runs:
        selected = runs[0]

    start, end = _default_period()
    return templates.TemplateResponse(
        request=request,
        name="insights.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "sections": list(INSIGHT_SECTIONS),
            "default_start": start.isoformat(),
            "default_end": end.isoformat(),
            "runs": [_run_view(r) for r in runs],
            "selected": _run_view(selected) if selected else None,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Form handlers
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/insights/run")
async def run_insights(
    request: Request,
    period_start: str = Form(default=""),
    period_end: str = Form(default=""),
    sections: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    start, end = _default_period()
    if period_start.strip() or period_end.strip():
        start, end = _parse_period(period_start or start.isoformat(), period_end or end.isoformat())
    chosen = [s for s in sections if s in INSIGHT_SECTIONS] or list(INSIGHT_SECTIONS)

    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        return RedirectResponse(url="/insights?error=no_llm_config", status_code=303)
    locale = detect_locale(request, user.locale)
    mode = get_prefs().llm_mode

    run = InsightRun(
        user_id=user.id,
        period_start=start,
        period_end=end,
        sections=chosen,
        status="completed",
    )
    db.add(run)
    await db.flush()

    try:
        result = await analyze_insights(
            db=db,
            user_id=user.id,
            llm_config=llm_config,
            sections=chosen,
            period_start=start,
            period_end=end,
            locale=locale,
            llm_mode=mode,
        )
        run.summary = result.get("summary") or None
        run.usage_tokens = result.get("_usage", {}).get("total_tokens", 0)
        run.usage_cost = result.get("_usage", {}).get("cost", 0.0)
        run.status = "completed"
        for finding in result.get("findings", []):
            db.add(
                InsightFinding(
                    run_id=run.id,
                    section=finding["section"],
                    title=finding["title"],
                    summary=finding["summary"],
                    used_data=finding.get("used_data") or [],
                )
            )
    except (JsonRepairError, ValueError, Exception) as exc:  # noqa: BLE001 — показываем ошибку пользователю
        logger.warning("insights run failed: %s", exc)
        run.status = "failed"
        run.error = str(exc)[:500]
    run.completed_at = None  # set by server default on insert path
    await db.flush()
    return RedirectResponse(url=f"/insights?run_id={run.id}", status_code=303)


@router.post("/insights/runs/{run_id}/delete")
async def delete_run_page(
    run_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a past run + its findings."""
    run = (
        await db.execute(select(InsightRun).where(InsightRun.id == run_id, InsightRun.user_id == user.id))
    ).scalar_one_or_none()
    if run is not None:
        await db.delete(run)
        await db.flush()
    return RedirectResponse(url="/insights", status_code=303)


@router.get("/insights/export-medical", response_class=HTMLResponse)
async def export_medical_report_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Selective Medical & Care Report Exporter (Step 42 / ADR-121)."""
    from app.models.care import CareCourse
    from app.models.medication import Medication

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    medications = (
        await db.execute(select(Medication).where(Medication.user_id == user.id))
    ).scalars().all()

    courses = (
        await db.execute(select(CareCourse).where(CareCourse.user_id == user.id))
    ).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="insights_medical_exporter.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "insights",
            "medications": medications,
            "courses": courses,
            "report": None,
        },
    )


@router.post("/insights/export-medical/generate", response_class=HTMLResponse)
async def export_medical_report_generate(
    request: Request,
    include_meds: list[str] = Form(default=[]),
    include_courses: list[str] = Form(default=[]),
    anonymize: bool = Form(default=False),
    period_days: int = Form(default=30),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates filtered medical report based on selected privacy inclusions/exclusions."""
    from app.models.care import CareCourse
    from app.models.medication import Medication

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    all_meds = (
        await db.execute(select(Medication).where(Medication.user_id == user.id))
    ).scalars().all()

    all_courses = (
        await db.execute(select(CareCourse).where(CareCourse.user_id == user.id))
    ).scalars().all()

    filtered_meds = [m for m in all_meds if str(m.id) in include_meds]
    filtered_courses = [c for c in all_courses if str(c.id) in include_courses]

    today_str = date.today().strftime("%Y-%m-%d")
    patient_name = "Анонимный Пациент (Private Record)" if anonymize else (user.email or "Пользователь")

    report_data = {
        "patient_name": patient_name,
        "generated_date": today_str,
        "medications": filtered_meds,
        "courses": filtered_courses,
        "period_days": period_days,
    }

    return templates.TemplateResponse(
        request=request,
        name="insights_medical_exporter.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "insights",
            "medications": all_meds,
            "courses": all_courses,
            "report": report_data,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("")
async def json_list_runs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    runs = (
        (
            await db.execute(
                select(InsightRun).where(InsightRun.user_id == user.id).order_by(InsightRun.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"total": len(runs), "runs": [_run_view(r) for r in runs[:50]]}


@json_router.get("/runs/{run_id}")
async def json_get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = (
        await db.execute(select(InsightRun).where(InsightRun.id == run_id, InsightRun.user_id == user.id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Insight run not found")
    return _run_view(run)


@json_router.delete("/runs/{run_id}", status_code=204)
async def json_delete_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить запуск анализа (findings — CASCADE) — для мобильного клиента."""
    run = (
        await db.execute(select(InsightRun).where(InsightRun.id == run_id, InsightRun.user_id == user.id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Insight run not found")
    await db.delete(run)
    await db.flush()
    return None


class InsightBody(BaseModel):
    period_start: date | None = None
    period_end: date | None = None
    sections: list[str] = Field(default_factory=list)


@json_router.post("", status_code=201)
async def json_run_insights(
    body: InsightBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start, end = _default_period()
    if body.period_start is not None or body.period_end is not None:
        start = body.period_start or start
        end = body.period_end or end
        if end < start:
            start, end = end, start
    chosen = [s for s in body.sections if s in INSIGHT_SECTIONS] or list(INSIGHT_SECTIONS)

    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        raise HTTPException(400, "No active LLM config — configure one in /llm-configs")
    mode = get_prefs().llm_mode

    run = InsightRun(user_id=user.id, period_start=start, period_end=end, sections=chosen)
    db.add(run)
    await db.flush()

    try:
        result = await analyze_insights(
            db=db,
            user_id=user.id,
            llm_config=llm_config,
            sections=chosen,
            period_start=start,
            period_end=end,
            locale=user.locale or "en",
            llm_mode=mode,
        )
        run.summary = result.get("summary") or None
        run.usage_tokens = result.get("_usage", {}).get("total_tokens", 0)
        run.usage_cost = result.get("_usage", {}).get("cost", 0.0)
        run.status = "completed"
        for finding in result.get("findings", []):
            db.add(
                InsightFinding(
                    run_id=run.id,
                    section=finding["section"],
                    title=finding["title"],
                    summary=finding["summary"],
                    used_data=finding.get("used_data") or [],
                )
            )
    except (JsonRepairError, ValueError, Exception) as exc:  # noqa: BLE001
        logger.warning("insights run failed: %s", exc)
        run.status = "failed"
        run.error = str(exc)[:500]
    await db.flush()
    # findings are lazy="selectin" — refresh the freshly created run so the
    # view can read them without a sync lazy load (async greenlet issue).
    await db.refresh(run, ["findings"])
    return _run_view(run)


@json_router.post("/export-report")
async def json_export_personal_report(
    days: int = Query(default=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """1-Click Medical / Personal Report Exporter (Step 26)."""
    from app.llm.pipeline.persona import generate_personal_medical_report

    report = await generate_personal_medical_report(db, user.id, days=days)
    return report


@json_router.get("/correlation-matrix")
async def json_correlation_matrix(
    days: int = Query(default=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns aggregated correlation matrix data for charts (Step 27)."""
    from app.models.health import HealthState
    from app.models.journal import JournalEntry, JournalPartner
    from app.models.locktimer import LockSession

    # Fetch health states
    h_stmt = (
        select(HealthState)
        .where(HealthState.user_id == user.id)
        .order_by(HealthState.event_date.asc())
        .limit(days)
    )
    health_states = (await db.execute(h_stmt)).scalars().all()

    health_matrix = []
    for h in health_states:
        health_matrix.append({
            "date": h.event_date.isoformat(),
            "mood": h.mood or 0,
            "energy": h.energy or 0,
            "sleep_hours": h.sleep_hours or 0,
            "post_session_drop": bool(h.post_session_drop),
            "hrt_taken": bool(h.hrt_taken),
        })

    # Fetch lock sessions
    locks_stmt = select(LockSession).where(LockSession.owner_id == user.id).limit(20)
    locks = (await db.execute(locks_stmt)).scalars().all()

    lock_matrix = []
    for lock_sess in locks:
        dur_h = 0.0
        if lock_sess.started_at and lock_sess.ended_at:
            dur_h = round((lock_sess.ended_at - lock_sess.started_at).total_seconds() / 3600.0, 1)
        lock_matrix.append({
            "lock_id": str(lock_sess.id)[:8],
            "status": lock_sess.status,
            "duration_hours": dur_h,
            "extensions_count": len(lock_sess.extension_history or []),
            "health_paused": lock_sess.is_health_paused,
        })

    # Fetch partner satisfaction
    partners_stmt = select(JournalPartner).where(JournalPartner.user_id == user.id)
    partners = (await db.execute(partners_stmt)).scalars().all()

    partner_matrix = []
    for p in partners:
        entries_stmt = select(func.avg(JournalEntry.satisfaction)).where(
            JournalEntry.user_id == user.id, JournalEntry.partner_id == p.id
        )
        avg_sat = (await db.execute(entries_stmt)).scalar() or 0.0
        partner_matrix.append({
            "partner_name": p.name,
            "roles": p.roles or [],
            "avg_satisfaction": round(float(avg_sat), 2),
        })

    return {
        "days": days,
        "health_matrix": health_matrix,
        "lock_matrix": lock_matrix,
        "partner_matrix": partner_matrix,
    }


@router.get("/insights/trajectory", response_class=HTMLResponse)
async def practice_trajectory_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Practice Trajectory & Mastery Radar Dashboard."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="insights_trajectory.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "insights",
        },
    )


@router.post("/insights/trajectory/generate-map")
async def generate_trajectory_map_endpoint(
    user: User = Depends(get_current_user),
):
    """Regenerates AI Trajectory Map from Agent."""
    return RedirectResponse(url="/insights/trajectory", status_code=303)

