"""Social subjects (S1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale
from app.models.user import User
from app.platform.social import get_adapter_registry
from app.platform.social.repositories import get_profile, list_owner_subjects
from app.templates_setup import templates

router = APIRouter(tags=["social"])


@router.get("/subjects", response_class=HTMLResponse)
async def social_subjects_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GET /social/subjects — list your registered social subjects."""
    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)
    profile = await get_profile(db, current_user.id)

    if profile is None:
        return RedirectResponse(url="/social/profile", status_code=303)

    subjects = await list_owner_subjects(db, current_user.id)
    adapters = get_adapter_registry()

    return templates.TemplateResponse(
        request,
        "social/subjects.html",
        {
            "t": t,
            "locale": locale,
            "user": current_user,
            "profile": profile,
            "subjects": subjects,
            "adapters": adapters,
        },
    )


@router.get("/api/capabilities")
async def social_capabilities():
    """GET /social/api/capabilities — adapter registry info (public, no auth)."""
    adapters = get_adapter_registry()
    result = {}
    for ns, adapter in adapters.items():
        result[ns] = {
            "version": adapter.version,
            "subject_types": adapter.subject_types(),
        }
    return result
