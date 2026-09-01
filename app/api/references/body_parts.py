"""Body parts reference API — read-only system catalog (REFACTORING.md step 3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.body_part import BodyPart
from app.models.user import User
from app.schemas.references import BodyPartOut, BodyPartTreeNode
from app.templates_setup import templates

router = APIRouter(tags=["body-parts"])
page_router = APIRouter(tags=["body-parts-page"])


@router.get("/body-parts", response_model=list[BodyPartOut])
async def list_body_parts(
    body_system: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Flat list of body parts, optionally filtered by system."""
    query = select(BodyPart).order_by(BodyPart.sort_order, BodyPart.title_ru)
    if body_system:
        query = query.where(BodyPart.body_system == body_system)
    if is_active is not None:
        query = query.where(BodyPart.is_active == is_active)
    result = await db.execute(query)
    return [BodyPartOut.model_validate(bp) for bp in result.scalars().all()]


@router.get("/body-parts/tree", response_model=list[BodyPartTreeNode])
async def body_parts_tree(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Hierarchical tree of body parts (for UI selectors)."""
    result = await db.execute(
        select(BodyPart).where(BodyPart.is_active.is_(True)).order_by(BodyPart.sort_order, BodyPart.title_ru)
    )
    all_parts = list(result.scalars().all())

    by_parent: dict[uuid.UUID | None, list[BodyPart]] = {}
    for bp in all_parts:
        by_parent.setdefault(bp.parent_id, []).append(bp)

    def _build(parent_id: uuid.UUID | None) -> list[BodyPartTreeNode]:
        nodes = []
        for bp in by_parent.get(parent_id, []):
            nodes.append(
                BodyPartTreeNode(
                    id=bp.id,
                    slug=bp.slug,
                    title_ru=bp.title_ru,
                    title_en=bp.title_en,
                    body_system=bp.body_system,
                    is_sensitive=bp.is_sensitive,
                    is_active=bp.is_active,
                    sort_order=bp.sort_order,
                    children=_build(bp.id),
                )
            )
        return nodes

    return _build(None)


@page_router.get("/body-parts", response_class=HTMLResponse)
@page_router.get("/body-parts/page", response_class=HTMLResponse)
async def body_parts_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Body parts catalog page with tree + search."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    tr = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="body_parts.html",
        context={
            "request": request,
            "t": tr,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "body_parts",
        },
    )


@router.get("/body-parts/{body_part_id}", response_model=BodyPartOut)
async def get_body_part(
    body_part_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(BodyPart).where(BodyPart.id == body_part_id))
    bp = result.scalar_one_or_none()
    if bp is None:
        raise HTTPException(404, "Body part not found")
    return BodyPartOut.model_validate(bp)
