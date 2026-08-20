"""Universal Activity Catalog API (ADR-091) — сквозной каталог активностей.

Единый справочник «видов активностей» (как Entity: категории/теги/описание),
на который ссылаются журнал/уход/таймер/трекер. Системные записи (owner_id NULL)
видны всем; пользовательские — только владельцу. Каталог нейтрален (relief-only,
PD-013): без игровой интеграции.

Страницы:
- GET  /catalog                        — просмотр каталога (системные + свои, фильтр по domain)
- POST /catalog/items                  — создать свою запись
- POST /catalog/items/{id}/delete      — удалить свою запись

JSON API (мобильный/bearer):
- GET  /api/v2/catalog                 — список (системные + свои, фильтр по domain)
- POST /api/v2/catalog/items           — создать свою запись

Хелпер ``catalog_options`` используется пикерами журнала/ухода/таймера/трекера.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
from app.templates_setup import templates

router = APIRouter(tags=["catalog"])
json_router = APIRouter(prefix="/api/v2/catalog", tags=["catalog"])


# ─────────────────────────────────────────────────────────────────────────────
# Shared helper — options for pickers in other modules
# ─────────────────────────────────────────────────────────────────────────────


async def catalog_options(
    db: AsyncSession,
    user_id: uuid.UUID,
    domain: str | None = None,
) -> list[dict]:
    """Возвращает [{id, name, owner_id}] видимых записей каталога.

    Видны: системные (owner_id NULL) + свои. Если ``domain`` задан — только
    записи, применимые в этом контексте (domains пусто/None = везде).
    """
    result = await db.execute(
        select(ActivityCatalogItem)
        .where(or_(ActivityCatalogItem.owner_id.is_(None), ActivityCatalogItem.owner_id == user_id))
        .order_by(ActivityCatalogItem.name.asc())
    )
    items = result.scalars().all()
    out: list[dict] = []
    for it in items:
        if domain and it.domains and domain not in it.domains:
            continue
        out.append(
            {
                "id": str(it.id),
                "name": it.name,
                "owner_id": str(it.owner_id) if it.owner_id else None,
            }
        )
    return out


def _validate_domains(raw: str) -> list[str] | None:
    """Разобрать строку domains формы (через запятую) в валидный список."""
    if not raw.strip():
        return None
    parsed = [d.strip() for d in raw.split(",") if d.strip()]
    parsed = [d for d in parsed if d in CATALOG_DOMAINS]
    return parsed or None


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────


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

    # Categories for the filter + create form
    cat_result = await db.execute(
        select(ActivityCategory).order_by(ActivityCategory.sort_order, ActivityCategory.title)
    )
    cats = cat_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="catalog_items.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "items": [
                {
                    "id": str(it.id),
                    "name": it.name,
                    "description": it.description,
                    "category_id": str(it.category_id) if it.category_id else None,
                    "category_title": it.category_rel.title if it.category_rel else None,
                    "tags": it.tags or [],
                    "domains": it.domains or [],
                    "is_system": it.owner_id is None,
                }
                for it in items
            ],
            "categories": [
                {"id": str(c.id), "title": c.title, "parent_id": str(c.parent_id) if c.parent_id else None}
                for c in cats
            ],
            "domains": list(CATALOG_DOMAINS),
            "active_domain": domain,
            "active_category_id": str(category_id) if category_id else None,
            "active_nav": "activity_catalog",
        },
    )


@router.get("/catalog/public", response_class=HTMLResponse)
async def public_catalog_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Public Catalog & Community Template Exchange (Step 78 / Audit A-03 fix)."""
    from sqlalchemy import or_

    result = await db.execute(
        select(ActivityCatalogItem)
        .where(
            or_(
                ActivityCatalogItem.owner_id.is_(None),
                ActivityCatalogItem.is_public.is_(True),
            )
        )
        .order_by(ActivityCatalogItem.name.asc())
    )
    items = result.scalars().all()

    locale = detect_locale(request, user.locale)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="catalog_public.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "active_nav": "activity_catalog",
            "items": items,
        },
    )


@router.post("/catalog/import-template")
async def import_public_template_endpoint(
    item_id: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Imports a public catalog template into user's personal catalog (Audit A-03 fix)."""
    try:
        template_uuid = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(400, "Invalid item_id UUID") from None

    template = (
        await db.execute(select(ActivityCatalogItem).where(ActivityCatalogItem.id == template_uuid))
    ).scalar_one_or_none()

    if not template:
        raise HTTPException(404, "Template item not found")

    new_item = ActivityCatalogItem(
        name=f"{template.name} (Копия)",
        description=template.description,
        category_id=template.category_id,
        tags=template.tags,
        domains=template.domains,
        owner_id=user.id,
        is_public=False,
    )
    db.add(new_item)
    await db.commit()

    return RedirectResponse(url="/entities/catalog", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Form handlers
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/catalog/items")
async def create_item(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    category_id: str = Form(default=""),
    tags: str = Form(default=""),
    domains: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
        name=name,
        description=(description or "").strip() or None,
        category_id=cat_uuid,
        tags=[x.strip() for x in tags.split(",") if x.strip()] if tags.strip() else None,
        domains=_validate_domains(domains),
        owner_id=user.id,
        is_public=False,
    )
    db.add(item)
    await db.flush()
    return RedirectResponse(url="/catalog", status_code=303)


@router.post("/catalog/items/{item_id}/delete")
async def delete_item(
    request: Request,
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить только свою запись (системные не удаляются)."""
    item = (
        await db.execute(
            select(ActivityCatalogItem).where(
                ActivityCatalogItem.id == item_id,
                ActivityCatalogItem.owner_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Catalog item not found")
    await db.delete(item)
    await db.flush()
    return RedirectResponse(url="/catalog", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("")
async def json_list(
    domain: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if domain and domain not in CATALOG_DOMAINS:
        domain = None
    items = await catalog_options(db, user.id, domain=domain)
    return {"total": len(items), "items": items}


class CatalogItemBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category_id: uuid.UUID | None = None
    tags: list[str] | None = None
    domains: list[str] | None = None


@json_router.post("/items", status_code=201)
async def json_create_item(
    body: CatalogItemBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")

    cat_uuid = None
    if body.category_id is not None:
        cat = (
            await db.execute(select(ActivityCategory).where(ActivityCategory.id == body.category_id))
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(400, "Category not found")
        cat_uuid = body.category_id

    domains = [d for d in (body.domains or []) if d in CATALOG_DOMAINS] or None

    item = ActivityCatalogItem(
        name=name,
        description=(body.description or "").strip() or None,
        category_id=cat_uuid,
        tags=[t.strip() for t in (body.tags or []) if t.strip()] or None,
        domains=domains,
        owner_id=user.id,
        is_public=False,
    )
    db.add(item)
    await db.flush()
    return {
        "id": str(item.id),
        "name": item.name,
        "description": item.description,
        "category_id": str(item.category_id) if item.category_id else None,
        "tags": item.tags or [],
        "domains": item.domains or [],
        "owner_id": str(item.owner_id) if item.owner_id else None,
    }


@json_router.delete("/items/{item_id}", status_code=204)
async def json_delete_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить только свою запись каталога (системные не удаляются)."""
    item = (
        await db.execute(
            select(ActivityCatalogItem).where(
                ActivityCatalogItem.id == item_id,
                ActivityCatalogItem.owner_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Catalog item not found")
    await db.delete(item)
    await db.flush()
    return None
