"""Settings — customization & discretion (Step 9e, DESIGN_V2 §16).

GET  /settings                  → settings.html (form state from prefs)
POST /settings                  → save all preferences (redirect back)
POST /settings/discretion/toggle → quick on/off discretion toggle (JSON)
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.prefs import DASH_BLOCKS, sanitize_prefs
from app.templates_setup import templates

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.prefs import prefs_from_dict

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    prefs = prefs_from_dict(user.prefs)

    response = templates.TemplateResponse(
        request,
        "settings.html",
        {
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "prefs": prefs,
            "dash_blocks": DASH_BLOCKS,
        },
    )
    from app.security import ensure_csrf_cookie

    ensure_csrf_cookie(request, response)
    return response


@router.post("/settings")
async def save_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    theme_choice: str = Form("dark"),
    accent: str = Form("ember"),
    density: str = Form("comfortable"),
    block_order: str = Form(""),
    block_hidden: str = Form(""),
    discretion_mode: str = Form("off"),
    discretion_start: str = Form("22:00"),
    discretion_end: str = Form("07:00"),
    blur: int = Form(0),
):
    """Save the full preference form. Values are validated by ``sanitize_prefs``."""
    raw = sanitize_prefs(
        {
            "theme_choice": theme_choice,
            "accent": accent,
            "density": density,
            "dash_blocks": {
                "order": [b.strip() for b in block_order.split(",") if b.strip()],
                "hidden": [b.strip() for b in block_hidden.split(",") if b.strip()],
            },
            "discretion": {
                "mode": discretion_mode,
                "start": discretion_start,
                "end": discretion_end,
            },
            "blur": blur,
        }
    )

    # keep the legacy theme column in sync (pages resolve theme via detect_theme)
    user.theme = raw["theme_choice"]
    user.prefs = raw
    db.add(user)

    referer = request.headers.get("referer", "/settings")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/settings/discretion/toggle")
async def toggle_discretion(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Quick toggle: off ↔ always (DESIGN_V2 §12 — instant switch, no reload).

    The server stays the source of truth for the next SSR; the client applies
    the visual state immediately via JS and swaps the favicon/title.
    """
    from app.prefs import raw_dict

    raw = sanitize_prefs(raw_dict(user.prefs))
    mode = "off" if raw["discretion"]["mode"] == "always" else "always"
    raw["discretion"]["mode"] = mode
    user.prefs = raw
    db.add(user)
    return JSONResponse({"mode": mode})
