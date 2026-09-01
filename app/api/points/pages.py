"""HTML pages — measurements, inventory, schedule, points."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(tags=["v2"])
page_router = APIRouter(tags=["pages"])


@page_router.get("/measurements", response_class=HTMLResponse)
@page_router.get("/measurements/page", response_class=HTMLResponse)
async def measurements_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="measurements.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "points"},
    )


@page_router.get("/inventory", response_class=HTMLResponse)
@page_router.get("/inventory/page", response_class=HTMLResponse)
async def inventory_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="inventory.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "inventory"},
    )


@page_router.get("/schedule", response_class=HTMLResponse)
@page_router.get("/schedule/page", response_class=HTMLResponse)
async def schedule_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="schedule.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "schedule"},
    )


@page_router.get("/points", response_class=HTMLResponse)
@page_router.get("/points/page", response_class=HTMLResponse)
async def points_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="points.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "points"},
    )
