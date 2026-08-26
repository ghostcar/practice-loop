"""Social profile + consent + privacy pages (S0)."""

from __future__ import annotations

from hashlib import sha256

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale
from app.models.user import User
from app.platform.social.repositories import (
    create_profile,
    get_profile,
    get_profile_by_alias,
    has_accepted_consent,
    record_consent,
    update_profile,
)
from app.templates_setup import templates

router = APIRouter(tags=["social"])

CURRENT_CONSENT_VERSION = 1


@router.get("/profile", response_class=HTMLResponse)
async def social_profile_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GET /social/profile — view/edit your social profile."""
    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)
    profile = await get_profile(db, current_user.id)

    from app.prefs import prefs_from_dict

    return templates.TemplateResponse(
        request,
        "social/profile.html",
        {
            "t": t,
            "locale": locale,
            "user": current_user,
            "profile": profile,
            "user_prefs": prefs_from_dict(current_user.prefs),
            "consent_accepted": await has_accepted_consent(db, current_user.id, CURRENT_CONSENT_VERSION),
            "consent_version": CURRENT_CONSENT_VERSION,
        },
    )


@router.post("/profile/create", response_class=HTMLResponse)
async def social_profile_create(
    request: Request,
    alias: str = Form(min_length=3, max_length=80),
    bio: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/profile/create — create social profile with alias."""

    # Validate alias — ASCII alphanumeric + underscore + hyphen only
    alias_stripped = alias.strip()
    if not alias_stripped:
        raise HTTPException(400, "Alias cannot be empty")
    for ch in alias_stripped:
        if not (ch.isascii() and (ch.isalnum() or ch in "_-")):
            raise HTTPException(400, "Alias must be alphanumeric, underscore, or hyphen")
    alias_normalized = alias_stripped.lower()

    # Check uniqueness
    existing = await get_profile_by_alias(db, alias_normalized)
    if existing is not None:
        raise HTTPException(409, "Alias already taken")

    # Check if user already has a profile
    if await get_profile(db, current_user.id) is not None:
        raise HTTPException(409, "Profile already exists")

    await create_profile(db, current_user.id, alias_stripped, alias_normalized, bio)

    return RedirectResponse(url="/social/profile", status_code=303)


@router.post("/profile/update", response_class=HTMLResponse)
async def social_profile_update(
    request: Request,
    bio: str | None = Form(None),
    discoverable: bool | None = Form(None),
    show_in_feed: bool | None = Form(None),
    auto_publish: bool | None = Form(None),
    auto_publish_visibility: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/profile/update — update profile fields."""
    await update_profile(db, current_user.id, bio=bio, discoverable=discoverable, show_in_feed=show_in_feed)

    # Auto-publish prefs live in users.prefs (no schema change needed).
    from app.prefs import raw_dict, sanitize_prefs

    prefs_changed = auto_publish is not None or auto_publish_visibility is not None
    if prefs_changed:
        merged = raw_dict(current_user.prefs)
        if auto_publish is not None:
            merged["social_auto_publish"] = auto_publish
        if auto_publish_visibility is not None:
            merged["social_auto_publish_visibility"] = auto_publish_visibility
        current_user.prefs = sanitize_prefs(merged)

    return RedirectResponse(url="/social/profile", status_code=303)


@router.post("/consent/accept", response_class=HTMLResponse)
async def social_consent_accept(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/consent/accept — accept privacy terms."""
    ip_hash = sha256((request.client.host if request.client else "unknown").encode()).hexdigest()[:64]
    await record_consent(db, current_user.id, CURRENT_CONSENT_VERSION, ip_hash)
    return RedirectResponse(url="/social/profile", status_code=303)


@router.get("/privacy", response_class=HTMLResponse)
async def social_privacy_page(request: Request):
    """GET /social/privacy — privacy policy (public, no auth required)."""
    locale = detect_locale(request)
    t = get_translations(locale)

    from app.auth import get_optional_user

    user = await get_optional_user(request)
    return templates.TemplateResponse(
        request,
        "social/privacy.html",
        {"t": t, "locale": locale, "user": user},
    )
