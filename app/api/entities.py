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


def _personalize_hint(schema: dict | list | None) -> dict:
    """Extract duration / reps bounds from ``params_schema`` for the personalize modal (R2.5).

    Supports both schema shapes (ADR-041): legacy compact map
    ``{"duration_minutes": {"min": 3, "max": 20, "unit": "minutes"}}`` and the
    structured definition list. Returns bounds converted to **seconds** for
    duration (unit-aware: hour/day/minute/second) and plain integers for reps.
    """
    hint = {"duration_min": None, "duration_max": None, "reps_min": None, "reps_max": None}
    if not schema:
        return hint

    if isinstance(schema, dict):
        defs: list[tuple[str, object]] = list(schema.items())
    else:
        defs = [(d.get("key", "") if isinstance(d, dict) else "", d) for d in schema]

    for key, rule in defs:
        if not isinstance(rule, dict):
            continue
        k = str(key).lower()
        typ = str(rule.get("type", "")).lower()
        is_dur = typ == "duration" or any(seg in k for seg in ("duration", "minute", "second", "hour", "day"))
        is_rep = (not is_dur) and (
            typ in ("integer", "number", "count") or any(seg in k for seg in ("rep", "count", "quant", "participant"))
        )
        if not (is_dur or is_rep):
            continue
        lo, hi = rule.get("min"), rule.get("max")
        mult = 1
        if is_dur:
            unit = str(rule.get("unit", "")).lower()
            if "hour" in unit:
                mult = 3600
            elif "minute" in unit:
                mult = 60
            elif "day" in unit:
                mult = 86400
            # else: seconds / unknown → keep as-is
        prefix = "duration" if is_dur else "reps"
        if hint[f"{prefix}_min"] is None and lo is not None:
            hint[f"{prefix}_min"] = int(lo) * mult
        if hint[f"{prefix}_max"] is None and hi is not None:
            hint[f"{prefix}_max"] = int(hi) * mult
    return hint


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

    # Personalize modal (R2.5): care products + inventory as soft-link selectors
    care_products: list[dict] = []
    try:
        from app.models.care import CareProduct

        cp_result = await db.execute(
            select(CareProduct).where(CareProduct.user_id == user.id).order_by(CareProduct.name).limit(200)
        )
        care_products = [{"id": str(p.id), "name": p.name} for p in cp_result.scalars().all()]
    except Exception:
        pass  # care module may not be deployed yet

    inventory_items: list[dict] = []
    try:
        from app.models.life import InventoryItem

        inv_result = await db.execute(
            select(InventoryItem)
            .where(InventoryItem.user_id == user.id, InventoryItem.inventory_status != "archived")
            .order_by(InventoryItem.name)
            .limit(200)
        )
        inventory_items = [
            {"id": str(i.id), "name": i.name, "category": i.category} for i in inv_result.scalars().all()
        ]
    except Exception:
        pass  # inventory module may not be deployed yet

    # Per-entity bounds (seconds for duration) for prefill of the modal
    personalize_hints = {str(e.id): _personalize_hint(e.params_schema) for e in entities}

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
            "care_products": care_products,
            "inventory_items": inventory_items,
            "personalize_hints": personalize_hints,
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

    # ADR-106: a personal entity is approved by the user by default — create an
    # opt-in row automatically so the entity is immediately eligible for LLM
    # generation, manual task creation and the scheduler (no separate opt-in
    # step needed). Explicit opt-out later is still respected.
    db.add(UserEntityOptIn(user_id=user.id, entity_id=entity.id, is_opted_in=True, desire_level="neutral"))
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


@router.get("/{entity_id}/edit", response_class=HTMLResponse)
async def edit_entity_page(
    request: Request,
    entity_id: uuid.UUID,
    error: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full-featured Entity Editor for params_schema and safety_contract (ADR-105/106)."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Only owner or admin can edit
    if entity.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission to edit this entity")

    # Load categories
    cat_result = await db.execute(select(ActivityCategory).where(ActivityCategory.is_active.is_(True)))
    categories = list(cat_result.scalars().all())

    # Load catalog items
    catalog_items = await catalog_options(db, user.id, domain="tracker")

    # Load care products
    care_products: list[dict] = []
    try:
        from app.models.care import CareProduct

        cp_result = await db.execute(
            select(CareProduct).where(CareProduct.user_id == user.id).order_by(CareProduct.name).limit(200)
        )
        care_products = [{"id": str(p.id), "name": p.name} for p in cp_result.scalars().all()]
    except Exception:
        pass

    import json

    params_json = json.dumps(entity.params_schema, indent=2, ensure_ascii=False) if entity.params_schema else ""
    safety_json = json.dumps(entity.safety_contract, indent=2, ensure_ascii=False) if entity.safety_contract else ""

    tags_str = ", ".join(entity.tags) if entity.tags else ""
    role_tags_str = ", ".join(entity.role_tags) if entity.role_tags else ""

    return templates.TemplateResponse(
        request=request,
        name="entity_edit.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "entity": entity,
            "categories": categories,
            "catalog_items": catalog_items,
            "care_products": care_products,
            "params_json": params_json,
            "safety_json": safety_json,
            "tags_str": tags_str,
            "role_tags_str": role_tags_str,
            "error": error,
            "active_nav": "catalog",
        },
    )


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
    """Save updated Entity configuration."""
    import json

    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission to edit this entity")

    # Validate type and risk_level
    if type not in ("one_time", "series", "infinite"):
        type = "one_time"
    if risk_level not in ("not_assessed", "low", "elevated", "high"):
        risk_level = "not_assessed"

    # Resolve category string
    category_str = entity.category
    if category_id is not None:
        cat_res = await db.execute(select(ActivityCategory).where(ActivityCategory.id == category_id))
        cat = cat_res.scalar_one_or_none()
        if cat is not None:
            category_str = cat.title

    # Parse params_schema JSON if provided
    params_schema = None
    if params_json.strip():
        try:
            params_schema = json.loads(params_json.strip())
            if not isinstance(params_schema, dict):
                raise ValueError("params_schema must be a JSON object")
        except Exception as exc:
            return RedirectResponse(
                url=f"/entities/{entity_id}/edit?error=Invalid+params_schema+JSON:+{str(exc)}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    # Parse safety_contract JSON if provided
    safety_contract = None
    if safety_json.strip():
        try:
            safety_contract = json.loads(safety_json.strip())
            if not isinstance(safety_contract, dict):
                raise ValueError("safety_contract must be a JSON object")
        except Exception as exc:
            return RedirectResponse(
                url=f"/entities/{entity_id}/edit?error=Invalid+safety_contract+JSON:+{str(exc)}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    # Resolve catalog_item_id
    catalog_uuid = None
    if catalog_item_id.strip():
        try:
            cid = uuid.UUID(catalog_item_id.strip())
            catalog_uuid = cid
        except ValueError:
            pass

    # Resolve care_product_ids
    care_uuids: list[str] | None = None
    if care_product_ids.strip():
        raw = [x.strip() for x in care_product_ids.split(",") if x.strip()]
        care_uuids = raw if raw else None

    # Update entity fields
    entity.real_name = real_name.strip()
    entity.short_title = short_title.strip() or None
    entity.slug = slugify(real_name)
    entity.type = type
    entity.category_id = category_id
    entity.category = category_str
    entity.risk_level = risk_level
    entity.adult_only = adult_only
    entity.automation_allowed = automation_allowed
    entity.penalty_enabled = penalty_enabled
    entity.is_public = is_public
    entity.tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    entity.role_tags = [r.strip() for r in role_tags.split(",") if r.strip()] if role_tags else None
    entity.params_schema = params_schema
    entity.safety_contract = safety_contract
    entity.catalog_item_id = catalog_uuid
    entity.care_product_ids = care_uuids

    db.add(entity)
    await db.flush()

    return RedirectResponse(url="/entities/catalog", status_code=status.HTTP_303_SEE_OTHER)


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
    """Personalize an activity into a user-owned fork (Fork-on-Opt-In, ADR-106 / Revision 2).

    When a user customizes parameters of a catalog item, it becomes a private
    user-owned Entity with their specific bounds, leaving the system template intact.
    """
    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user.id),
        )
    )
    base_entity = ent_result.scalar_one_or_none()
    if base_entity is None:
        raise HTTPException(status_code=404, detail="Activity entity not found")

    # Build custom params schema dictionary
    custom_params: dict = dict(base_entity.params_schema or {})
    if duration_min is not None or duration_max is not None:
        dur_dict = custom_params.setdefault("duration_min", {})
        if isinstance(dur_dict, dict):
            if duration_min is not None:
                dur_dict["min"] = duration_min
            if duration_max is not None:
                dur_dict["max"] = duration_max
    if reps_min is not None or reps_max is not None:
        reps_dict = custom_params.setdefault("reps", {})
        if isinstance(reps_dict, dict):
            if reps_min is not None:
                reps_dict["min"] = reps_min
            if reps_max is not None:
                reps_dict["max"] = reps_max

    care_ids = [x.strip() for x in assigned_care_ids.split(",") if x.strip()] if assigned_care_ids else None
    inventory_ids = [
        x.strip() for x in assigned_inventory_ids.split(",") if x.strip()
    ] if assigned_inventory_ids else None
    if inventory_ids:
        # R2.5: inventory selector → typed param (ADR-041 inventory_selector)
        custom_params["inventory_ids"] = {
            "type": "inventory_selector",
            "title": "Inventory",
            "selection_mode": "multiple",
            "required": False,
            "value": inventory_ids,
        }

    # Check if this is already a user-owned entity
    if base_entity.owner_id == user.id:
        if custom_name.strip():
            base_entity.real_name = custom_name.strip()
        base_entity.params_schema = custom_params
        if care_ids is not None:
            base_entity.care_product_ids = care_ids
        target_entity = base_entity
    else:
        # Check if user already has a personal fork of this base entity
        fork_res = await db.execute(
            select(Entity).where(Entity.owner_id == user.id, Entity.parent_id == base_entity.id)
        )
        forked = fork_res.scalar_one_or_none()
        if forked is not None:
            if custom_name.strip():
                forked.real_name = custom_name.strip()
            forked.params_schema = custom_params
            if care_ids is not None:
                forked.care_product_ids = care_ids
            target_entity = forked
        else:
            target_entity = Entity(
                owner_id=user.id,
                parent_id=base_entity.id,
                catalog_item_id=base_entity.catalog_item_id,
                real_name=custom_name.strip() or f"{base_entity.real_name} (Моя настройка)",
                slug=slugify(custom_name.strip() or base_entity.real_name),
                type=base_entity.type,
                category=base_entity.category,
                category_id=base_entity.category_id,
                tags=base_entity.tags,
                role_tags=base_entity.role_tags,
                intensity=base_entity.intensity,
                risk_level=base_entity.risk_level,
                adult_only=base_entity.adult_only,
                automation_allowed=True,
                is_public=False,
                params_schema=custom_params,
                care_product_ids=care_ids or base_entity.care_product_ids,
            )
            db.add(target_entity)
            await db.flush()

    # Upsert opt-in for target entity
    oi_res = await db.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == user.id,
            UserEntityOptIn.entity_id == target_entity.id,
        )
    )
    opt_in = oi_res.scalar_one_or_none()
    if opt_in is None:
        opt_in = UserEntityOptIn(
            user_id=user.id,
            entity_id=target_entity.id,
            is_opted_in=is_opted_in,
            desire_level=desire_level if desire_level in DESIRE_LEVELS else "want",
        )
        db.add(opt_in)
    else:
        opt_in.is_opted_in = is_opted_in
        if desire_level in DESIRE_LEVELS:
            opt_in.desire_level = desire_level
        from datetime import datetime

        opt_in.updated_at = datetime.now(UTC)

    await db.flush()
    referer = request.headers.get("referer", "/entities/catalog")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)
