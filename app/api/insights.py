"""Personal Insights API (M3 Personal Suite, Шаг 17, ROADMAP §7 4E).

All business logic lives in app.services.insights_service (ADR-168).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.insights import INSIGHT_SECTIONS
from app.models.user import User
from app.services import insights_service as svc
from app.templates_setup import templates
from app.timeutils import local_today

router = APIRouter(tags=["insights"])
json_router = APIRouter(prefix="/api/v2/insights", tags=["insights"])


# Re-export for dashboard_service (ADR-168)
_insights_summary = svc.insights_summary


# ─────────────────────────────────────────────────────────────────────────────
# HTML Pages
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

    try:
        ctx = await svc.get_insights_page_context(db, user.id, run_id)
    except Exception:
        raise HTTPException(404, "Insight run not found") from None

    return templates.TemplateResponse(
        request=request,
        name="insights.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            **ctx,
        },
    )


@router.post("/insights/run")
async def run_insights(
    request: Request,
    period_start: str = Form(default=""),
    period_end: str = Form(default=""),
    sections: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    start, end = svc.default_period()
    if period_start.strip() or period_end.strip():
        try:
            start, end = svc.parse_period(period_start or start.isoformat(), period_end or end.isoformat())
        except ValueError as e:
            return RedirectResponse(url=f"/insights?error={e}", status_code=303)

    chosen = [s for s in sections if s in INSIGHT_SECTIONS] or list(INSIGHT_SECTIONS)
    locale = detect_locale(request, user.locale)

    try:
        run = await svc.execute_insight_run(db, user.id, start=start, end=end, chosen=chosen, locale=locale)
        return RedirectResponse(url=f"/insights?run_id={run.id}", status_code=303)
    except ValueError as e:
        return RedirectResponse(url=f"/insights?error={e}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/insights?error={e}", status_code=303)


@router.post("/insights/runs/{run_id}/delete")
async def delete_run_page(
    run_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_insight_run(db, run_id, user.id)
    return RedirectResponse(url="/insights", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Medical exporter
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/insights/export-medical", response_class=HTMLResponse)
async def export_medical_report_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    med_ctx = await svc.get_medical_export_context(db, user.id)

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
            **med_ctx,
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
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    med_ctx = await svc.get_medical_export_context(db, user.id)
    report = svc.generate_medical_report(
        user,
        med_ctx["medications"],
        med_ctx["courses"],
        include_meds=include_meds,
        include_courses=include_courses,
        anonymize=anonymize,
        period_days=period_days,
    )

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
            **med_ctx,
            "report": report,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Static pages (no business logic)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/insights/trajectory", response_class=HTMLResponse)
async def practice_trajectory_page(
    request: Request,
    user: User = Depends(get_current_user),
):
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
    return RedirectResponse(url="/insights/trajectory", status_code=303)


@router.get("/insights/report", response_class=HTMLResponse)
async def insights_report_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    stats = await svc.get_report_stats(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="insights_report.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "stats": stats,
            "today": local_today().isoformat(),
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
    runs = await svc.get_insights_page_context(db, user.id)
    return {"total": len(runs["runs"]), "runs": runs["runs"][:50]}


@json_router.get("/runs/{run_id}")
async def json_get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from sqlalchemy import select as _select

    from app.models.insights import InsightRun

    stmt = _select(InsightRun).where(InsightRun.id == run_id, InsightRun.user_id == user.id)
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Insight run not found")
    return svc.run_view(run)


@json_router.delete("/runs/{run_id}", status_code=204)
async def json_delete_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = await svc.delete_insight_run(db, run_id, user.id)
    if not deleted:
        raise HTTPException(404, "Insight run not found")
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
    start, end = svc.default_period()
    if body.period_start is not None or body.period_end is not None:
        start = body.period_start or start
        end = body.period_end or end
        if end < start:
            start, end = end, start

    chosen = [s for s in body.sections if s in INSIGHT_SECTIONS] or list(INSIGHT_SECTIONS)

    try:
        run = await svc.execute_insight_run(
            db,
            user.id,
            start=start,
            end=end,
            chosen=chosen,
            locale=user.locale or "en",
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None

    await db.refresh(run, ["findings"])
    return svc.run_view(run)


@json_router.post("/export-report")
async def json_export_personal_report(
    days: int = Query(default=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.llm.pipeline.persona import generate_personal_medical_report

    report = await generate_personal_medical_report(db, user.id, days=days)
    return report


@json_router.get("/correlation-matrix")
async def json_correlation_matrix(
    days: int = Query(default=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.get_correlation_matrix(db, user.id, days)
