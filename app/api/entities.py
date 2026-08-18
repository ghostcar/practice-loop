import uuid
from datetime import UTC

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.catalog import catalog_options
from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.catalog import ActivityCatalogItem
from app.models.category import ActivityCategory
from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn
from app.models.user import User
from app.schemas.entity import DESIRE_LEVELS
from app.slugify import slugify
from app.templates_setup import templates

router = APIRouter(prefix="/entities", tags=["entities"])


# --- Category tree helpers ---


def _build_category_tree(
    cats: list[ActivityCategory],
) -> tuple[list[ActivityCategory], dict[uuid.UUID, list[ActivityCategory]]]:
    """Split categories into top-level roots and a parent→children map."""
    ids = {c.id for c in cats}
    roots: list[ActivityCategory] = []
    children: dict[uuid.UUID, list[ActivityCategory]] = {}
    for c in cats:
        if c.parent_id and c.parent_id in ids:
            children.setdefault(c.parent_id, []).append(c)
        else:
            roots.append(c)
    roots.sort(key=lambda c: (c.sort_order, c.title))
    for k in children:
        children[k].sort(key=lambda c: (c.sort_order, c.title))
    return roots, children


def _category_and_descendants(cat_id: uuid.UUID, cats: list[ActivityCategory]) -> set[uuid.UUID]:
    """Selected category + all of its descendants (for subtree filtering)."""
    result: set[uuid.UUID] = set()
    stack = [cat_id]
    while stack:
        cur = stack.pop()
        if cur in result:
            continue
        result.add(cur)
        for c in cats:
            if c.parent_id == cur:
                stack.append(c.id)
    return result


# --- Pages ---


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    category: str | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Browse the entity catalog — hierarchical ActivityCategory filters (ADR-035).

    Filtering is by ``category_id`` (the normalized table). The legacy
    ``category`` string filter is kept for backward compatibility with old
    links and entities that still only carry the string.
    """
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    # Load the full category tree (for filter chips)
    cat_result = await db.execute(select(ActivityCategory).where(ActivityCategory.is_active.is_(True)))
    all_categories = list(cat_result.scalars().all())
    root_categories, subcategories = _build_category_tree(all_categories)
    # Template-friendly: string-keyed subcategory map
    subcategories = {str(k): v for k, v in subcategories.items()}

    query = select(Entity).where(Entity.is_public | (Entity.owner_id == user.id))
    active_category_id: uuid.UUID | None = None
    active_category_str: str | None = None

    if category_id:
        active_category_id = category_id
        ids = _category_and_descendants(category_id, all_categories)
        query = query.where(Entity.category_id.in_(ids))
    elif category:
        # Legacy string filter (backward compat)
        active_category_str = category
        query = query.where(Entity.category == category)

    result = await db.execute(query.order_by(Entity.category, Entity.real_name))
    entities = result.scalars().all()

    # Get user's opt-ins
    opt_in_result = await db.execute(select(UserEntityOptIn).where(UserEntityOptIn.user_id == user.id))
    opt_ins = {oi.entity_id: oi for oi in opt_in_result.scalars().all()}

    # Legacy unique category strings (fallback chips for non-normalized entities)
    legacy_cats_result = await db.execute(select(Entity.category).distinct().order_by(Entity.category))
    legacy_categories = [row[0] for row in legacy_cats_result.all()]

    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "entities": entities,
            "opt_ins": opt_ins,
            "root_categories": root_categories,
            "subcategories": subcategories,
            "legacy_categories": legacy_categories,
            "active_category_id": str(active_category_id) if active_category_id else None,
            "active_category_str": active_category_str,
            "desire_levels": DESIRE_LEVELS,
            "active_nav": "catalog",
        },
    )


@router.get("/my", response_class=HTMLResponse)
async def my_entities_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User's personal entities."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(
        select(Entity).where(Entity.owner_id == user.id).order_by(Entity.category, Entity.real_name)
    )
    entities = result.scalars().all()

    # Сквозной каталог (ADR-091): пикер видов активностей (домен tracker).
    catalog_items = await catalog_options(db, user.id, domain="tracker")

    # Средства/косметика (ADR-094): задача может требовать использования средства.
    care_products: list[dict] = []
    try:
        from app.models.care import CareProduct

        cp_result = await db.execute(
            select(CareProduct).where(CareProduct.user_id == user.id).order_by(CareProduct.name).limit(200)
        )
        care_products = [{"id": str(p.id), "name": p.name} for p in cp_result.scalars().all()]
    except Exception:
        pass  # care module may not be deployed yet

    return templates.TemplateResponse(
        request=request,
        name="my_entities.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "entities": entities,
            "catalog_items": catalog_items,
            "care_products": care_products,
            "active_nav": "catalog",
        },
    )


# --- CRUD API ---


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
    """Create a new entity."""
    if type not in ("one_time", "series", "infinite"):
        type = "one_time"
    if risk_level not in ("not_assessed", "low", "elevated", "high"):
        risk_level = "not_assessed"
    if category_id is not None:
        # Normalized category — resolve the legacy display string for back-compat
        cat_result = await db.execute(select(ActivityCategory).where(ActivityCategory.id == category_id))
        cat = cat_result.scalar_one_or_none()
        if cat is not None:
            category = cat.title
    # Сквозной каталог (ADR-091): задача может быть основана на универсальном виде
    catalog_uuid = None
    if catalog_item_id.strip():
        try:
            cid = uuid.UUID(catalog_item_id.strip())
        except ValueError as exc:
            raise HTTPException(422, "Invalid catalog_item_id format") from exc
        item = (
            await db.execute(
                select(ActivityCatalogItem).where(
                    ActivityCatalogItem.id == cid,
                    ActivityCatalogItem.owner_id.is_(None) | (ActivityCatalogItem.owner_id == user.id),
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(400, "Catalog item not found")
        catalog_uuid = cid
    # Средства/косметика (ADR-094): какие средства нужны для задачи.
    care_uuids: list[uuid.UUID] | None = None
    if care_product_ids.strip():
        from app.models.care import CareProduct

        raw = [x.strip() for x in care_product_ids.split(",") if x.strip()]
        try:
            parsed = [uuid.UUID(x) for x in raw]
        except ValueError as exc:
            raise HTTPException(422, "Invalid care_product_ids format") from exc
        if parsed:
            rows = (
                (
                    await db.execute(
                        select(CareProduct.id).where(CareProduct.id.in_(parsed), CareProduct.user_id == user.id)
                    )
                )
                .scalars()
                .all()
            )
            if len(rows) != len(set(parsed)):
                raise HTTPException(400, "One or more care products not found")
            # JSON-колонка: храним строки (UUID не сериализуется в JSON)
            care_uuids = [str(x) for x in parsed]

    entity = Entity(
        type=type,
        real_name=real_name.strip(),
        slug=slugify(real_name),
        category=category.strip(),
        category_id=category_id,
        catalog_item_id=catalog_uuid,
        care_product_ids=care_uuids,
        tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else None,
        owner_id=user.id,
        is_public=is_public,
        author_id=user.id if is_public else None,
        risk_level=risk_level,
    )
    db.add(entity)
    await db.flush()

    referer = request.headers.get("referer", "/entities/my")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{entity_id}/publish")
async def publish_entity(
    request: Request,
    entity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish a personal entity (make it public)."""
    result = await db.execute(select(Entity).where(Entity.id == entity_id, Entity.owner_id == user.id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity.is_public = True
    entity.author_id = user.id
    db.add(entity)

    referer = request.headers.get("referer", "/entities/my")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{entity_id}/delete")
async def delete_entity(
    request: Request,
    entity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a personal entity."""
    result = await db.execute(select(Entity).where(Entity.id == entity_id, Entity.owner_id == user.id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    await db.delete(entity)

    referer = request.headers.get("referer", "/entities/my")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


# --- Opt-in API ---


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
    """Set or update opt-in preference for an entity (public or owned only)."""
    # Verify entity exists AND is public or owned by user
    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user.id),
        )
    )
    if ent_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Upsert opt-in
    result = await db.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == user.id,
            UserEntityOptIn.entity_id == entity_id,
        )
    )
    opt_in = result.scalar_one_or_none()

    if opt_in is None:
        opt_in = UserEntityOptIn(
            user_id=user.id,
            entity_id=entity_id,
            is_opted_in=is_opted_in,
            rating=rating if 1 <= (rating or 0) <= 5 else None,
            desire_level=desire_level if desire_level in DESIRE_LEVELS else "neutral",
        )
    else:
        opt_in.is_opted_in = is_opted_in
        if rating is not None and 1 <= rating <= 5:
            opt_in.rating = rating
        if desire_level in DESIRE_LEVELS:
            opt_in.desire_level = desire_level

    from datetime import datetime

    opt_in.updated_at = datetime.now(UTC)
    db.add(opt_in)
    await db.flush()

    referer = request.headers.get("referer", "/entities/catalog")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)
