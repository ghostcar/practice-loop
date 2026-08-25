"""Settings — customization & discretion (Step 9e, DESIGN_V2 §16).

GET  /settings                  → settings.html (form state from prefs)
POST /settings                  → save all preferences (redirect back)
POST /settings/discretion/toggle → quick on/off discretion toggle (JSON)
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, hash_password, verify_password
from app.config import settings as app_settings
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.api_token import ApiToken
from app.models.user import User
from app.prefs import DASH_BLOCKS, PROFILE_MODULES, sanitize_prefs
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
            "settings": app_settings,
            "profile_modules": PROFILE_MODULES,
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
    llm_mode: str = Form("safe"),
    reminder_time: str = Form(""),
    reminder_tz: str = Form(""),
    enabled_modules: list[str] = Form(default=[]),
    tab: str = Form("appearance"),
    med_gamification: str = Form("off"),
):
    """Save the full preference form. Values are validated by ``sanitize_prefs``."""
    # Preserve onboarding_completed flag across saves (form doesn't carry it).
    old_raw = user.prefs if isinstance(user.prefs, dict) else {}
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
            "llm_mode": llm_mode,
            "enabled_modules": enabled_modules,
            "reminder_time": reminder_time,
            "reminder_tz": reminder_tz,
            # ADR-137: checkbox sends "on" only when checked; unchecked =
            # missing field → "off". Stored as bool by sanitize_prefs.
            "med_gamification": med_gamification == "on",
            # P0: preserve onboarding flag
            "onboarding_completed": old_raw.get("onboarding_completed", False),
        }
    )

    # keep the legacy theme column in sync (pages resolve theme via detect_theme)
    user.theme = raw["theme_choice"]
    user.prefs = raw
    db.add(user)

    # Enabling a module is allowed only after its one-time consent. Save the
    # preference first, then route the user to the missing disclosures.
    from app.consent import missing_consents

    required = [f"module:{name}" for name in raw["enabled_modules"]]
    missing = await missing_consents(db, user.id, required)
    if llm_mode == "expanded":
        missing.extend(await missing_consents(db, user.id, ["llm_expanded"]))
        if "llm_expanded" in missing:
            raw["llm_mode"] = "safe"
            user.prefs = raw
    if missing:
        return RedirectResponse(url="/consent/setup?required=" + ",".join(missing), status_code=303)

    # Preserve the active tab after save
    safe_tab = tab if tab in ("appearance", "dashboard", "modules", "privacy", "security", "billing") else "appearance"
    return RedirectResponse(url=f"/settings?tab={safe_tab}&saved=1", status_code=303)


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


@router.post("/settings/password")
async def change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change the current user's password and revoke all mobile refresh tokens."""
    if not verify_password(current_password, user.password_hash):
        return RedirectResponse(url="/settings?password_status=invalid", status_code=303)
    if not 6 <= len(new_password) <= 128:
        return RedirectResponse(url="/settings?password_status=length", status_code=303)
    if new_password != confirm_password:
        return RedirectResponse(url="/settings?password_status=mismatch", status_code=303)
    if verify_password(new_password, user.password_hash):
        return RedirectResponse(url="/settings?password_status=same", status_code=303)

    user.password_hash = hash_password(new_password)
    db.add(user)
    await db.execute(delete(ApiToken).where(ApiToken.user_id == user.id))
    return RedirectResponse(url="/settings?password_status=changed", status_code=303)


@router.get("/discretion/bailout", response_class=HTMLResponse)
async def discretion_bailout_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Emergency Discretion & Stealth Control Center page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="discretion_bailout.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "settings",
        },
    )


@router.post("/discretion/toggle")
async def toggle_discretion_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Quick toggle for Discretion Stealth Mode."""
    from app.prefs import raw_dict

    raw = sanitize_prefs(raw_dict(user.prefs))
    mode = "off" if raw.get("discretion", {}).get("mode") == "always" else "always"
    raw["discretion"]["mode"] = mode
    user.prefs = raw
    db.add(user)
    await db.flush()
    return RedirectResponse(url="/discretion/bailout", status_code=303)


@router.get("/settings/pin-form", response_class=HTMLResponse)
async def pin_form_fragment(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """HTMX fragment: PIN management form (set / change / clear)."""
    locale = detect_locale(request, user.locale)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="components/pin_form_fragment.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "has_pin": user.pin_hash is not None,
            "pin_status": request.query_params.get("pin_status"),
        },
    )
