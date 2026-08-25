"""Entities Catalog — Thin HTTP routes.

All business logic lives in app.services.entities_service (ADR-165).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.entity import Entity
from app.models.user import User
from app.services import entities_service as svc
from app.services.errors import NotFoundError
from app.templates_setup import templates

router = APIRouter(prefix="/entities", tags=["entities"])


# ─────────────────────────────────────────────────────────────────────────────
# HTML Pages
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def entities_root_redirect():
    """Redirect /entities/ to /entities/catalog."""
    return RedirectResponse(url="/entities/catalog", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    category: str | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Auto-seed system catalog for new users — entity bootstrap only.
    # Opt-in + LLM presets are handled in onboarding (ADR-179).
    exists = await db.execute(select(Entity).where(Entity.owner_id.is_(None)).limit(1))
    if not exists.scalar_one_or_none():
        from app.seed import seed_entities

        await seed_entities(db)

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_catalog_page_context(db, user, category=category, category_id=category_id)
    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, **ctx},
    )


@router.get("/my", response_class=HTMLResponse)
async def my_entities_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_my_entities_page_context(db, user)
    return templates.TemplateResponse(
        request=request,
        name="my_entities.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, **ctx},
    )


@router.get("/{entity_id}/edit", response_class=HTMLResponse)
async def edit_entity_page(
    request: Request,
    entity_id: uuid.UUID,
    error: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    try:
        ctx = await svc.get_edit_entity_context(db, entity_id, user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None
    if ctx is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return templates.TemplateResponse(
        request=request,
        name="entity_edit.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "error": error, **ctx},
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML Form Handlers
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/")
async def create_entity(
    request: Request,
    real_name: str = Form(...),
    type: str = Form(default="one_time"),
    category: str = Form(default="other"),
    tags: str = Form(default=""),
    is_public: bool = Form(default=False),
    risk_level: str = Form(default="not_assessed"),
    category_id: uuid.UUID | None = Form(default=None),
    catalog_item_id: str = Form(default=""),
    care_product_ids: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_entity(
            db,
            user_id=user.id,
            real_name=real_name,
            type=type,
            category=category,
            tags=tags,
            is_public=is_public,
            risk_level=risk_level,
            category_id=category_id,
            catalog_item_id=catalog_item_id,
            care_product_ids=care_product_ids,
        )
    except (ValueError, NotFoundError) as e:
        raise HTTPException(400, str(e)) from None
    referer = request.headers.get("referer", "/entities/my")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{entity_id}/publish")
async def publish_entity(
    request: Request,
    entity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.publish_entity(db, user.id, entity_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    referer = request.headers.get("referer", "/entities/my")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{entity_id}/delete")
async def delete_entity(
    request: Request,
    entity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_entity(db, user.id, entity_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    referer = request.headers.get("referer", "/entities/my")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{entity_id}/edit")
async def update_entity(
    request: Request,
    entity_id: uuid.UUID,
    real_name: str = Form(...),
    short_title: str = Form(default=""),
    type: str = Form(default="one_time"),
    category_id: uuid.UUID | None = Form(default=None),
    risk_level: str = Form(default="not_assessed"),
    adult_only: bool = Form(default=False),
    automation_allowed: bool = Form(default=False),
    penalty_enabled: bool = Form(default=True),
    is_public: bool = Form(default=False),
    tags: str = Form(default=""),
    role_tags: str = Form(default=""),
    params_json: str = Form(default=""),
    safety_json: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    care_product_ids: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.update_entity(
            db,
            user_id=user.id,
            user_role=user.role,
            entity_id=entity_id,
            real_name=real_name,
            short_title=short_title,
            type=type,
            category_id=category_id,
            risk_level=risk_level,
            adult_only=adult_only,
            automation_allowed=automation_allowed,
            penalty_enabled=penalty_enabled,
            is_public=is_public,
            tags=tags,
            role_tags=role_tags,
            params_json=params_json,
            safety_json=safety_json,
            catalog_item_id=catalog_item_id,
            care_product_ids=care_product_ids,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None
    except ValueError as e:
        return RedirectResponse(
            url=f"/entities/{entity_id}/edit?error=Invalid+JSON:+{str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(url="/entities/catalog", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{entity_id}/opt-in")
async def toggle_opt_in(
    request: Request,
    entity_id: uuid.UUID,
    is_opted_in: bool = Form(default=True),
    rating: int | None = Form(default=None),
    desire_level: str = Form(default="neutral"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.toggle_opt_in(
            db,
            user_id=user.id,
            entity_id=entity_id,
            is_opted_in=is_opted_in,
            rating=rating,
            desire_level=desire_level,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    referer = request.headers.get("referer", "/entities/catalog")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{entity_id}/personalize")
async def personalize_entity(
    request: Request,
    entity_id: uuid.UUID,
    custom_name: str = Form(default=""),
    duration_min: int | None = Form(default=None),
    duration_max: int | None = Form(default=None),
    reps_min: int | None = Form(default=None),
    reps_max: int | None = Form(default=None),
    desire_level: str = Form(default="want"),
    is_opted_in: bool = Form(default=True),
    assigned_care_ids: str = Form(default=""),
    assigned_inventory_ids: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.personalize_entity(
            db,
            user_id=user.id,
            entity_id=entity_id,
            custom_name=custom_name,
            duration_min=duration_min,
            duration_max=duration_max,
            reps_min=reps_min,
            reps_max=reps_max,
            desire_level=desire_level,
            is_opted_in=is_opted_in,
            assigned_care_ids=assigned_care_ids,
            assigned_inventory_ids=assigned_inventory_ids,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    referer = request.headers.get("referer", "/entities/catalog")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)
