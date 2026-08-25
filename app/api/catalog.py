"""Universal Activity Catalog — thin HTTP wrappers over app.services.catalog_service."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale
from app.models.catalog import CATALOG_DOMAINS, ActivityCatalogItem
from app.models.category import ActivityCategory
from app.models.user import User
from app.services.catalog_service import catalog_options, validate_domains
from app.templates_setup import templates

router = APIRouter(tags=["catalog"])
json_router = APIRouter(prefix="/api/v2/catalog", tags=["catalog"])

# Re-export shared helper for pickers in other modules
__all__ = ["router", "json_router", "catalog_options"]


class CatalogItemBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    domains: str | list = Field(default="")
    category_id: str = Field(default="")
    tags: str = Field(default="")


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    domain: str | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    t = get_translations(locale)

    if domain and domain not in CATALOG_DOMAINS:
        domain = None

    query = select(ActivityCatalogItem).where(
        or_(ActivityCatalogItem.owner_id.is_(None), ActivityCatalogItem.owner_id == user.id)
    )
    if category_id:
        query = query.where(ActivityCatalogItem.category_id == category_id)
    result = await db.execute(query.order_by(ActivityCatalogItem.name.asc()))
    items = result.scalars().all()

    if domain:
        items = [it for it in items if not it.domains or domain in it.domains]

    cat_result = await db.execute(
        select(ActivityCategory).order_by(ActivityCategory.sort_order, ActivityCategory.title)
    )
    cats = cat_result.scalars().all()

    return templates.TemplateResponse(
        request=request, name="catalog_items.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale,
            "items": [{
                "id": str(it.id), "name": it.name,
                "description": it.description,
                "category_id": str(it.category_id) if it.category_id else None,
                "category_title": it.category_rel.title if it.category_rel else None,
                "tags": it.tags or [], "domains": it.domains or [],
                "is_system": it.owner_id is None,
            } for it in items],
            "CATALOG_DOMAINS": CATALOG_DOMAINS,
            "selected_domain": domain,
            "categories": cats,
        },
    )


@router.post("/catalog/items")
async def create_item(
    request: Request, name: str = Form(...),
    description: str = Form(default=""), category_id: str = Form(default=""),
    tags: str = Form(default=""), domains: str = Form(default=""),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    name = name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")

    cat_uuid = None
    if category_id.strip():
        try:
            cat_uuid = uuid.UUID(category_id.strip())
        except ValueError:
            raise HTTPException(400, "Invalid category_id") from None
        cat = (await db.execute(select(ActivityCategory).where(ActivityCategory.id == cat_uuid))).scalar_one_or_none()
        if cat is None:
            raise HTTPException(400, "Category not found")

    item = ActivityCatalogItem(
        name=name, description=(description or "").strip() or None,
        category_id=cat_uuid,
        tags=[x.strip() for x in tags.split(",") if x.strip()] if tags.strip() else None,
        domains=validate_domains(domains),
        owner_id=user.id, is_public=False,
    )
    db.add(item)
    await db.flush()
    return RedirectResponse(url="/catalog", status_code=303)


@router.post("/catalog/items/{item_id}/delete")
async def delete_item(
    item_id: uuid.UUID, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(
        select(ActivityCatalogItem).where(
            ActivityCatalogItem.id == item_id, ActivityCatalogItem.owner_id == user.id,
        )
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    await db.delete(item)
    return RedirectResponse(url="/catalog", status_code=303)


@router.get("/catalog/public", response_class=HTMLResponse)
async def public_catalog_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Public catalog — system items visible to all with import capability."""
    locale = detect_locale(request, user.locale)
    items_result = await db.execute(
        select(ActivityCatalogItem)
        .where(ActivityCatalogItem.owner_id.is_(None), ActivityCatalogItem.is_public.is_(True))
        .order_by(ActivityCatalogItem.name.asc())
    )
    items = items_result.scalars().all()
    return templates.TemplateResponse(request=request, name="catalog_public.html", context={
        "request": request, "t": get_translations(locale), "user": user,
        "locale": locale, "items": items, "active_nav": "catalog",
    })


# JSON API
@json_router.get("")
async def json_list_catalog(
    domain: str | None = Query(default=None),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if domain and domain not in CATALOG_DOMAINS:
        domain = None
    items = await catalog_options(db, user.id, domain=domain)
    return {"total": len(items), "items": items}


@json_router.post("/items", status_code=201)
async def json_create_item(
    body: CatalogItemBody, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cat_uuid = None
    if body.category_id.strip():
        try:
            cat_uuid = uuid.UUID(body.category_id.strip())
        except ValueError:
            raise HTTPException(400, "Invalid category_id")
    domains_val = body.domains if isinstance(body.domains, list) else validate_domains(body.domains)
    item = ActivityCatalogItem(
        owner_id=user.id, name=body.name, description=body.description,
        category_id=cat_uuid,
        tags=[x.strip() for x in body.tags.split(",") if x.strip()] if body.tags.strip() else None,
        domains=domains_val,
        is_public=False,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return JSONResponse({
        "id": str(item.id), "name": item.name,
        "owner_id": str(item.owner_id),
    }, status_code=201)


@json_router.delete("/items/{item_id}", status_code=204)
async def json_delete_item(
    item_id: uuid.UUID, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(
        select(ActivityCatalogItem).where(
            ActivityCatalogItem.id == item_id, ActivityCatalogItem.owner_id == user.id,
        )
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    await db.delete(item)
    return JSONResponse(None, status_code=204)