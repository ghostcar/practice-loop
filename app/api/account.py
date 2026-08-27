"""Authenticated account profile."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import get_current_user
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(tags=["account"])


@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, user: User = Depends(get_current_user)):
    locale = detect_locale(request, user.locale)
    return templates.TemplateResponse(
        request,
        "account.html",
        {
            "t": get_translations(locale),
            "theme": detect_theme(user.theme),
            "user": user,
            "locale": locale,
            "nav_key": "account",
        },
    )
