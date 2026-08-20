"""API Router for Public Digital Achievement Certificates Verification."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/certificates", tags=["certificates"])


@router.get("/{cert_id}/verify", response_class=HTMLResponse)
async def verify_certificate_page(
    request: Request,
    cert_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Public Digital Achievement Certificate Verification Page."""
    locale = detect_locale(request, None)
    theme = detect_theme("dark")
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="certificate.html",
        context={
            "request": request,
            "t": t,
            "cert_id": cert_id,
            "locale": locale,
            "theme": theme,
            "is_valid": True,
            "program_title": "14-Дневная Адаптивная Программа Практик",
        },
    )
