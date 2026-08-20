"""API Router for AI Agent Persona Builder UI."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.persona_builder import get_or_create_user_persona, update_user_persona_config
from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["persona_builder"])


@router.get("/persona-builder", response_class=HTMLResponse)
async def persona_builder_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI Agent Persona Builder & Customization UI Page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    persona = await get_or_create_user_persona(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="persona_builder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "persona_builder",
            "persona": persona,
        },
    )


@router.post("/persona-builder")
async def save_persona_builder(
    persona_type: str = Form("caring_curator"),
    strictness_level: int = Form(3),
    tone_of_voice: str = Form("supportive_formal"),
    proactive_frequency: str = Form("daily"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Saves updated AI Agent persona settings."""
    await update_user_persona_config(
        db,
        user.id,
        persona_type=persona_type,
        strictness_level=strictness_level,
        tone_of_voice=tone_of_voice,
        proactive_frequency=proactive_frequency,
    )
    return RedirectResponse(url="/agent/persona-builder", status_code=303)
