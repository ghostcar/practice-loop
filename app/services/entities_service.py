"""Entities Catalog — Business Logic Service Layer.

Extracted from app/api/entities.py (ADR-165) to keep routers thin:
all CRUD, validation, serialization, and domain queries live here.

Public API:
  - get_catalog_page_context / get_my_entities_page_context
  - create_entity / publish_entity / delete_entity / update_entity
  - toggle_opt_in / personalize_entity
  - category helpers (build_category_tree, category_and_descendants)
  - personalize_hint
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import ActivityCatalogItem
from app.models.category import ActivityCategory
from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn
from app.schemas.entity import DESIRE_LEVELS
from app.services.errors import NotFoundError
from app.slugify import slugify

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Category tree helpers
# ─────────────────────────────────────────────────────────────────────────────


def build_category_tree(
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


def category_and_descendants(cat_id: uuid.UUID, cats: list[ActivityCategory]) -> set[uuid.UUID]:
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


def personalize_hint(schema: dict | list | None) -> dict:
    """Extract duration / reps bounds from params_schema for personalize modal (R2.5)."""
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
        prefix = "duration" if is_dur else "reps"
        if hint[f"{prefix}_min"] is None and lo is not None:
            hint[f"{prefix}_min"] = int(lo) * mult
        if hint[f"{prefix}_max"] is None and hi is not None:
            hint[f"{prefix}_max"] = int(hi) * mult
    return hint


# ─────────────────────────────────────────────────────────────────────────────
# Validators / resolvers
# ─────────────────────────────────────────────────────────────────────────────


async def resolve_catalog_item(
    db: AsyncSession, catalog_item_id: str | uuid.UUID | None, user_id: uuid.UUID
) -> uuid.UUID | None:
    if not catalog_item_id:
        return None
    try:
        cid = uuid.UUID(str(catalog_item_id))
    except ValueError:
        raise ValueError("Invalid catalog_item_id format") from None
    item = (
        await db.execute(
            select(ActivityCatalogItem).where(
                ActivityCatalogItem.id == cid,
                ActivityCatalogItem.owner_id.is_(None) | (ActivityCatalogItem.owner_id == user_id),
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Catalog item not found")
    return cid


async def resolve_care_products(
    db: AsyncSession, care_product_ids: str, user_id: uuid.UUID
) -> list[str] | None:
    if not care_product_ids.strip():
        return None
    from app.models.care import CareProduct

    raw = [x.strip() for x in care_product_ids.split(",") if x.strip()]
    try:
        parsed = [uuid.UUID(x) for x in raw]
    except ValueError:
        raise ValueError("Invalid care_product_ids format") from None
    if not parsed:
        return None
    rows = (
        (await db.execute(select(CareProduct.id).where(CareProduct.id.in_(parsed), CareProduct.user_id == user_id)))
        .scalars()
        .all()
    )
    if len(rows) != len(set(parsed)):
        raise NotFoundError("One or more care products not found")
    return [str(x) for x in parsed]


async def get_opt_ins(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, UserEntityOptIn]:
    result = await db.execute(select(UserEntityOptIn).where(UserEntityOptIn.user_id == user_id))
    return {oi.entity_id: oi for oi in result.scalars().all()}


async def get_care_products(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    try:
        from app.models.care import CareProduct

        cp_result = await db.execute(
            select(CareProduct).where(CareProduct.user_id == user_id).order_by(CareProduct.name).limit(200)
        )
        return [{"id": str(p.id), "name": p.name} for p in cp_result.scalars().all()]
    except Exception:
        return []


async def get_inventory_items(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    try:
        from app.models.life import InventoryItem

        inv_result = await db.execute(
            select(InventoryItem)
            .where(InventoryItem.user_id == user_id, InventoryItem.inventory_status != "archived")
            .order_by(InventoryItem.name)
            .limit(200)
        )
        return [{"id": str(i.id), "name": i.name, "category": i.category} for i in inv_result.scalars().all()]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Page context builders
# ─────────────────────────────────────────────────────────────────────────────


async def get_catalog_page_context(
    db: AsyncSession, user, *, category: str | None = None, category_id: uuid.UUID | None = None
) -> dict:

    cat_result = await db.execute(select(ActivityCategory).where(ActivityCategory.is_active.is_(True)))
    all_categories = list(cat_result.scalars().all())
    root_categories, subcategories = build_category_tree(all_categories)
    subcategories = {str(k): v for k, v in subcategories.items()}

    query = select(Entity).where(Entity.is_public | (Entity.owner_id == user.id))
    active_category_id: uuid.UUID | None = None
    active_category_str: str | None = None

    if category_id:
        active_category_id = category_id
        ids = category_and_descendants(category_id, all_categories)
        query = query.where(Entity.category_id.in_(ids))
    elif category:
        active_category_str = category
        query = query.where(Entity.category == category)

    result = await db.execute(query.order_by(Entity.category, Entity.real_name))
    entities = result.scalars().all()

    opt_ins = await get_opt_ins(db, user.id)
    care_products = await get_care_products(db, user.id)
    inventory_items = await get_inventory_items(db, user.id)

    personalize_hints = {str(e.id): personalize_hint(e.params_schema) for e in entities}

    legacy_cats_result = await db.execute(select(Entity.category).distinct().order_by(Entity.category))
    legacy_categories = [row[0] for row in legacy_cats_result.all()]

    return {
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
    }


async def get_my_entities_page_context(db: AsyncSession, user) -> dict:
    from app.services.catalog_service import catalog_options

    result = await db.execute(
        select(Entity).where(Entity.owner_id == user.id).order_by(Entity.category, Entity.real_name)
    )
    entities = result.scalars().all()
    catalog_items = await catalog_options(db, user.id, domain="tracker")
    care_products = await get_care_products(db, user.id)

    return {
        "entities": entities,
        "catalog_items": catalog_items,
        "care_products": care_products,
        "active_nav": "catalog",
    }


async def get_edit_entity_context(db: AsyncSession, entity_id: uuid.UUID, user) -> dict | None:
    from app.services.catalog_service import catalog_options

    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        return None

    if entity.owner_id != user.id and user.role != "admin":
        raise PermissionError("You do not have permission to edit this entity")

    cat_result = await db.execute(select(ActivityCategory).where(ActivityCategory.is_active.is_(True)))
    categories = list(cat_result.scalars().all())
    catalog_items = await catalog_options(db, user.id, domain="tracker")
    care_products = await get_care_products(db, user.id)

    params_json = json.dumps(entity.params_schema, indent=2, ensure_ascii=False) if entity.params_schema else ""
    safety_json = json.dumps(entity.safety_contract, indent=2, ensure_ascii=False) if entity.safety_contract else ""
    tags_str = ", ".join(entity.tags) if entity.tags else ""
    role_tags_str = ", ".join(entity.role_tags) if entity.role_tags else ""

    return {
        "entity": entity,
        "categories": categories,
        "catalog_items": catalog_items,
        "care_products": care_products,
        "params_json": params_json,
        "safety_json": safety_json,
        "tags_str": tags_str,
        "role_tags_str": role_tags_str,
        "active_nav": "catalog",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Entities
# ─────────────────────────────────────────────────────────────────────────────


async def create_entity(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    real_name: str,
    type: str,
    category: str,
    tags: str,
    is_public: bool,
    risk_level: str,
    category_id: uuid.UUID | None,
    catalog_item_id: str,
    care_product_ids: str,
) -> Entity:
    if type not in ("one_time", "series", "infinite"):
        type = "one_time"
    if risk_level not in ("not_assessed", "low", "elevated", "high"):
        risk_level = "not_assessed"
    if category_id is not None:
        cat_result = await db.execute(select(ActivityCategory).where(ActivityCategory.id == category_id))
        cat = cat_result.scalar_one_or_none()
        if cat is not None:
            category = cat.title

    catalog_uuid = await resolve_catalog_item(db, catalog_item_id, user_id) if catalog_item_id.strip() else None
    care_uuids = await resolve_care_products(db, care_product_ids, user_id) if care_product_ids.strip() else None

    entity = Entity(
        type=type,
        real_name=real_name.strip(),
        slug=slugify(real_name),
        category=category.strip(),
        category_id=category_id,
        catalog_item_id=catalog_uuid,
        care_product_ids=care_uuids,
        tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else None,
        owner_id=user_id,
        is_public=is_public,
        author_id=user_id if is_public else None,
        risk_level=risk_level,
    )
    db.add(entity)
    await db.flush()

    # ADR-106: auto opt-in for personal entities
    db.add(UserEntityOptIn(user_id=user_id, entity_id=entity.id, is_opted_in=True, desire_level="neutral"))
    await db.flush()
    return entity


async def publish_entity(db: AsyncSession, user_id: uuid.UUID, entity_id: uuid.UUID) -> None:
    result = await db.execute(select(Entity).where(Entity.id == entity_id, Entity.owner_id == user_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError("Entity not found")
    entity.is_public = True
    entity.author_id = user_id
    db.add(entity)
    await db.flush()


async def delete_entity(db: AsyncSession, user_id: uuid.UUID, entity_id: uuid.UUID) -> None:
    result = await db.execute(select(Entity).where(Entity.id == entity_id, Entity.owner_id == user_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError("Entity not found")
    await db.delete(entity)
    await db.flush()


async def update_entity(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    user_role: str,
    entity_id: uuid.UUID,
    real_name: str,
    short_title: str,
    type: str,
    category_id: uuid.UUID | None,
    risk_level: str,
    adult_only: bool,
    automation_allowed: bool,
    penalty_enabled: bool,
    is_public: bool,
    tags: str,
    role_tags: str,
    params_json: str,
    safety_json: str,
    catalog_item_id: str,
    care_product_ids: str,
) -> Entity:
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError("Entity not found")
    if entity.owner_id != user_id and user_role != "admin":
        raise PermissionError("You do not have permission to edit this entity")

    if type not in ("one_time", "series", "infinite"):
        type = "one_time"
    if risk_level not in ("not_assessed", "low", "elevated", "high"):
        risk_level = "not_assessed"

    category_str = entity.category
    if category_id is not None:
        cat_res = await db.execute(select(ActivityCategory).where(ActivityCategory.id == category_id))
        cat = cat_res.scalar_one_or_none()
        if cat is not None:
            category_str = cat.title

    params_schema = None
    if params_json.strip():
        params_schema = json.loads(params_json.strip())
        if not isinstance(params_schema, dict):
            raise ValueError("params_schema must be a JSON object")

    safety_contract = None
    if safety_json.strip():
        safety_contract = json.loads(safety_json.strip())
        if not isinstance(safety_contract, dict):
            raise ValueError("safety_contract must be a JSON object")

    catalog_uuid = None
    if catalog_item_id.strip():
        with contextlib.suppress(ValueError):
            catalog_uuid = uuid.UUID(catalog_item_id.strip())

    care_uuids: list[str] | None = None
    if care_product_ids.strip():
        raw = [x.strip() for x in care_product_ids.split(",") if x.strip()]
        care_uuids = raw if raw else None

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
    return entity


# ─────────────────────────────────────────────────────────────────────────────
# Opt-in
# ─────────────────────────────────────────────────────────────────────────────


async def toggle_opt_in(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entity_id: uuid.UUID,
    is_opted_in: bool,
    rating: int | None,
    desire_level: str,
) -> None:
    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user_id),
        )
    )
    if ent_result.scalar_one_or_none() is None:
        raise NotFoundError("Entity not found")

    result = await db.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == user_id,
            UserEntityOptIn.entity_id == entity_id,
        )
    )
    opt_in = result.scalar_one_or_none()

    if opt_in is None:
        opt_in = UserEntityOptIn(
            user_id=user_id,
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

    opt_in.updated_at = datetime.now(UTC)
    db.add(opt_in)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Personalize (Fork-on-Opt-In, ADR-106)
# ─────────────────────────────────────────────────────────────────────────────


async def personalize_entity(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entity_id: uuid.UUID,
    custom_name: str,
    duration_min: int | None,
    duration_max: int | None,
    reps_min: int | None,
    reps_max: int | None,
    desire_level: str,
    is_opted_in: bool,
    assigned_care_ids: str,
    assigned_inventory_ids: str,
) -> None:
    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user_id),
        )
    )
    base_entity = ent_result.scalar_one_or_none()
    if base_entity is None:
        raise NotFoundError("Activity entity not found")

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
        custom_params["inventory_ids"] = {
            "type": "inventory_selector",
            "title": "Inventory",
            "selection_mode": "multiple",
            "required": False,
            "value": inventory_ids,
        }

    if base_entity.owner_id == user_id:
        if custom_name.strip():
            base_entity.real_name = custom_name.strip()
        base_entity.params_schema = custom_params
        if care_ids is not None:
            base_entity.care_product_ids = care_ids
        target_entity = base_entity
    else:
        fork_res = await db.execute(
            select(Entity).where(Entity.owner_id == user_id, Entity.parent_id == base_entity.id)
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
                owner_id=user_id,
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

    oi_res = await db.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == user_id,
            UserEntityOptIn.entity_id == target_entity.id,
        )
    )
    opt_in = oi_res.scalar_one_or_none()
    if opt_in is None:
        opt_in = UserEntityOptIn(
            user_id=user_id,
            entity_id=target_entity.id,
            is_opted_in=is_opted_in,
            desire_level=desire_level if desire_level in DESIRE_LEVELS else "want",
        )
        db.add(opt_in)
    else:
        opt_in.is_opted_in = is_opted_in
        if desire_level in DESIRE_LEVELS:
            opt_in.desire_level = desire_level
        opt_in.updated_at = datetime.now(UTC)

    await db.flush()
