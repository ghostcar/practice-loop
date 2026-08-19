"""PracticeLoop Autonomous Agent Router (Step 44 / ADR-123)."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.core import run_practice_agent
from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/chat", response_class=HTMLResponse)
async def agent_chat_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Interactive Agent Chat & Tool Execution Workbench."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="agent_chat.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "agent",
            "messages": [],
        },
    )


@router.post("/chat/message", response_class=HTMLResponse)
async def agent_chat_message(
    request: Request,
    prompt: str = Form(...),
    persona_role: str = Form(default="keyholder"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Processes user prompt via PracticeLoop Agent ReAct Tool Loop."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    res = await run_practice_agent(
        user_prompt=prompt,
        user_id=user.id,
        db=db,
        persona_role=persona_role,
    )

    return templates.TemplateResponse(
        request=request,
        name="agent_chat.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "agent",
            "messages": [{"user": prompt, "reply": res["reply"], "tools": res["tool_calls"]}],
            "persona_role": persona_role,
        },
    )
