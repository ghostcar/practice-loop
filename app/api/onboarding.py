"""Onboarding Wizard — thin HTTP handlers for new-user setup flow (P0).

Business logic lives in app/services/onboarding_service.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services.onboarding_service import (
    complete_onboarding,
    get_onboarding_context,
    is_onboarding_complete,
)
from app.templates_setup import templates

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """3-step onboarding wizard for new users."""
    # Already completed? Skip.
    if is_onboarding_complete(user.prefs):
        return RedirectResponse(url="/dashboard", status_code=303)

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = get_onboarding_context(user)

    return templates.TemplateResponse(
        request=request,
        name="onboarding.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            **ctx,
        },
    )


@router.post("/onboarding/complete")
async def onboarding_complete(
    request: Request,
    modules: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save module choices, mark onboarding complete, proceed to consent."""
    await complete_onboarding(db, user, enabled_modules=modules if modules else None)

    # After onboarding, go through consent for enabled modules
    from app.config import settings
    from app.consent import missing_consents
    from app.prefs import sanitize_prefs

    module_keys = [f"module:{name}" for name in sanitize_prefs(user.prefs)["enabled_modules"]]
    missing = await missing_consents(db, user.id, module_keys)

    if missing:
        return RedirectResponse(
            url="/consent/setup?required=" + ",".join(missing), status_code=303
        )
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/onboarding/skip")
async def onboarding_skip(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Skip onboarding — mark complete with defaults."""
    await complete_onboarding(db, user)
    return RedirectResponse(url="/dashboard", status_code=303)