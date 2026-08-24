"""Locations API — system catalog + user-custom CRUD (REFACTORING.md step 3)."""

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
from app.models.task_location import TaskLocation, TaskLocationUsage
from app.models.user import User
from app.schemas.references import (
    TaskLocationCreate,
    TaskLocationOut,
    TaskLocationTreeNode,
    TaskLocationUpdate,
)
from app.templates_setup import templates

router = APIRouter(tags=["locations"])


@router.get("/locations", response_model=list[TaskLocationOut])
async def list_locations(
    location_type: str | None = Query(default=None),
    privacy_level: str | None = Query(default=None),
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List locations: system (is_custom=False) + current user's custom."""
    query = select(TaskLocation).where((TaskLocation.is_custom.is_(False)) | (TaskLocation.owner_id == user.id))
    if location_type:
        query = query.where(TaskLocation.location_type == location_type)
    if privacy_level:
        query = query.where(TaskLocation.privacy_level == privacy_level)
    if not include_inactive:
        query = query.where(TaskLocation.is_active.is_(True))
    query = query.order_by(TaskLocation.sort_order, TaskLocation.title_ru)
    result = await db.execute(query)
    return [TaskLocationOut.model_validate(loc) for loc in result.scalars().all()]


@router.get("/locations/tree", response_model=list[TaskLocationTreeNode])
async def locations_tree(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Hierarchical tree of locations (system + user's custom)."""
    result = await db.execute(
        select(TaskLocation)
        .where(
            (TaskLocation.is_custom.is_(False)) | (TaskLocation.owner_id == user.id),
            TaskLocation.is_active.is_(True),
        )
        .order_by(TaskLocation.sort_order, TaskLocation.title_ru)
    )
    all_locs = list(result.scalars().all())

    by_parent: dict[uuid.UUID | None, list[TaskLocation]] = {}
    for loc in all_locs:
        by_parent.setdefault(loc.parent_id, []).append(loc)

    def _build(parent_id: uuid.UUID | None) -> list[TaskLocationTreeNode]:
        nodes = []
        for loc in by_parent.get(parent_id, []):
            nodes.append(
                TaskLocationTreeNode(
                    id=loc.id,
                    slug=loc.slug,
                    title_ru=loc.title_ru,
                    title_en=loc.title_en,
                    location_type=loc.location_type,
                    privacy_level=loc.privacy_level,
                    is_active=loc.is_active,
                    is_custom=loc.is_custom,
                    owner_id=loc.owner_id,
                    sort_order=loc.sort_order,
                    children=_build(loc.id),
                )
            )
        return nodes

    return _build(None)


@router.post("/locations", response_model=TaskLocationOut)
async def create_location(
    data: TaskLocationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a personal location."""
    # Check slug uniqueness
    existing = await db.execute(select(TaskLocation.id).where(TaskLocation.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Location with slug '{data.slug}' already exists")

    loc = TaskLocation(
        slug=data.slug,
        title_ru=data.title_ru,
        title_en=data.title_en,
        description=data.description,
        parent_id=data.parent_id,
        location_type=data.location_type,
        privacy_level=data.privacy_level,
        is_custom=True,
        owner_id=user.id,
        sort_order=data.sort_order,
    )
    db.add(loc)
    await db.flush()
    await db.refresh(loc)
    return TaskLocationOut.model_validate(loc)


@router.put("/locations/{location_id}", response_model=TaskLocationOut)
async def update_location(
    location_id: uuid.UUID,
    data: TaskLocationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a personal location. System locations are read-only."""
    result = await db.execute(
        select(TaskLocation).where(TaskLocation.id == location_id, TaskLocation.owner_id == user.id)
    )
    loc = result.scalar_one_or_none()
    if loc is None:
        raise HTTPException(404, "Location not found or not editable")
    if not loc.is_custom:
        raise HTTPException(403, "System locations cannot be edited")

    for k, v in data.model_dump(exclude_none=True).items():
        setattr(loc, k, v)
    db.add(loc)
    await db.flush()
    await db.refresh(loc)
    return TaskLocationOut.model_validate(loc)


@router.post("/locations/{location_id}/archive")
async def archive_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft-delete (archive) a personal location."""
    result = await db.execute(
        select(TaskLocation).where(TaskLocation.id == location_id, TaskLocation.owner_id == user.id)
    )
    loc = result.scalar_one_or_none()
    if loc is None:
        raise HTTPException(404, "Location not found or not editable")
    if not loc.is_custom:
        raise HTTPException(403, "System locations cannot be archived")

    loc.is_active = False
    db.add(loc)
    await db.flush()
    return {"status": "archived"}


@router.delete("/locations/{location_id}")
async def delete_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Hard-delete a personal location (only if no task references exist)."""
    result = await db.execute(
        select(TaskLocation).where(TaskLocation.id == location_id, TaskLocation.owner_id == user.id)
    )
    loc = result.scalar_one_or_none()
    if loc is None:
        raise HTTPException(404, "Location not found or not editable")
    if not loc.is_custom:
        raise HTTPException(403, "System locations cannot be deleted")

    # Check for task references
    refs = await db.execute(select(TaskLocationUsage.id).where(TaskLocationUsage.location_id == location_id).limit(1))
    if refs.scalar_one_or_none():
        raise HTTPException(409, "Location has task references — archive it instead")

    await db.delete(loc)
    return {"status": "deleted"}


page_router = APIRouter(tags=["locations-page"])


@page_router.get("/locations", response_class=HTMLResponse)
@page_router.get("/locations/page", response_class=HTMLResponse)
@router.get("/locations/page", response_class=HTMLResponse)
async def locations_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Locations catalog page with tree + CRUD."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="locations.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "locations",
        },
    )
