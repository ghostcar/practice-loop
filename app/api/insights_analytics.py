"""API Router for All-Inclusive Analytical Correlation Engine (Insights Engine v2)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.engine import run_full_analytics_suite
from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["insights_analytics"])


@router.get("/insights/analytics", response_class=HTMLResponse)
async def insights_analytics_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analytics Cockpit UI Page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    results = await run_full_analytics_suite(db, user.id, days=30, locale=locale)

    return templates.TemplateResponse(
        request=request,
        name="insights_analytics.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "insights_analytics",
            "analytics": results,
        },
    )


@router.post("/insights/analytics/run")
async def run_analytics_endpoint(
    days: int = Form(30),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Executes 10-module pairwise correlation analysis and persists dynamic InsightFinding entries."""
    if days < 7 or days > 365:
        raise HTTPException(400, "Days period must be between 7 and 365")

    results = await run_full_analytics_suite(db, user.id, days=days, locale=user.locale)
    return JSONResponse({"status": "ok", "analytics": results})


@router.get("/api/v2/analytics/matrix")
async def get_analytics_matrix_api(
    days: int = 30,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """REST JSON endpoint returning full pairwise matrix for mobile/PWA."""
    results = await run_full_analytics_suite(db, user.id, days=days, locale=user.locale)
    return JSONResponse(results)
