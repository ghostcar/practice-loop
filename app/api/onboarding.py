"""Onboarding Wizard — thin HTTP handlers for new-user setup flow (P0).

Business logic lives in app/services/onboarding_service.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.portal import get_portal_providers
from app.models.entity import Entity
from app.models.llm_catalog import LLMUserSelection
from app.models.llm_config import LLMProviderConfig
from app.models.opt_in import UserEntityOptIn
from app.models.user import User
from app.security import ensure_csrf_cookie
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
    """4-step onboarding wizard for new users."""
    # Already completed? Skip.
    if is_onboarding_complete(user.prefs):
        return RedirectResponse(url="/dashboard", status_code=303)

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = get_onboarding_context(user)

    # Portal LLM providers available for quick-pick on step 1.
    portal_providers = get_portal_providers()
    # Existing capability selections (so we can show "already selected").
    sel_result = await db.execute(select(LLMUserSelection).where(LLMUserSelection.user_id == user.id))
    llm_selections = {s.capability: s for s in sel_result.scalars().all()}
    llm_status = request.query_params.get("llm")
    requested_mode = request.query_params.get("mode")
    current_mode = requested_mode if requested_mode in {"none", "portal", "personal"} else ctx["ai_participation"]
    ctx["ai_participation"] = current_mode
    try:
        initial_step = max(1, min(4, int(request.query_params.get("step", "1"))))
    except (TypeError, ValueError):
        initial_step = 1

    response = templates.TemplateResponse(
        request=request,
        name="onboarding.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "portal_providers": portal_providers,
            "llm_selections": llm_selections,
            "llm_status": llm_status,
            "initial_step": initial_step,
            **ctx,
        },
    )
    # Issue a CSRF cookie so the quick-pick POST on step 1 succeeds.
    ensure_csrf_cookie(request, response)
    return response


@router.post("/onboarding/complete")
async def onboarding_complete(
    request: Request,
    modules: list[str] = Form(default=[]),
    ai_participation: str = Form(default="portal"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save module + AI participation choices, mark onboarding complete, bootstrap catalog + LLM."""
    await complete_onboarding(
        db,
        user,
        enabled_modules=modules if modules else None,
        ai_participation=ai_participation,
    )

    # Bootstrap: seed system entities, auto-opt-in, seed LLM presets (ADR-179)
    await _bootstrap_new_user(db, user)

    # After onboarding, go through consent for enabled modules
    from app.consent import missing_consents
    from app.prefs import sanitize_prefs

    module_keys = [f"module:{name}" for name in sanitize_prefs(user.prefs)["enabled_modules"]]
    missing = await missing_consents(db, user.id, module_keys)

    if missing:
        return RedirectResponse(url="/consent/setup?required=" + ",".join(missing), status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/onboarding/skip")
async def onboarding_skip(
    request: Request,
    ai_participation: str = Form(default="portal"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Skip onboarding — mark complete with defaults."""
    await complete_onboarding(db, user, ai_participation=ai_participation)
    await _bootstrap_new_user(db, user)
    return RedirectResponse(url="/dashboard", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap: seed data for new users (ADR-179)
# ─────────────────────────────────────────────────────────────────────────────


async def _bootstrap_new_user(db: AsyncSession, user: User) -> None:
    """Seed entities + LLM presets + auto-opt-in for a new user.

    Idempotent — safe to call multiple times.
    """
    # 1. Seed system catalog entities if none exist
    exists = await db.execute(select(Entity).where(Entity.owner_id.is_(None)).limit(1))
    if not exists.scalar_one_or_none():
        from app.seed import seed_entities

        await seed_entities(db)

    # 2. Auto-opt-in to all public entities (neutral desire)
    has_any = await db.execute(select(UserEntityOptIn.id).where(UserEntityOptIn.user_id == user.id).limit(1))
    if not has_any.scalar_one_or_none():
        all_public = await db.execute(select(Entity).where(Entity.is_public.is_(True)))
        for entity in all_public.scalars().all():
            db.add(
                UserEntityOptIn(
                    user_id=user.id,
                    entity_id=entity.id,
                    is_opted_in=True,
                    desire_level="neutral",
                )
            )

    # 3. Seed LLM provider presets (Omniroute + Groq + OpenRouter)
    has_cfg = await db.execute(select(LLMProviderConfig.id).where(LLMProviderConfig.user_id == user.id).limit(1))
    if not has_cfg.scalar_one_or_none():
        from app.seed import seed_llm_presets

        await seed_llm_presets(db, user_id=user.id)

    await db.flush()
    await db.commit()
    # Restart sub-transaction for the remainder of the request
    await db.begin()
