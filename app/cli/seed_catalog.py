"""CLI-сидер каталога (R2.1, REFACTOR_ROADMAP_V2.md).

Читает ВСЕ JSON-манифесты из ``data/seed/`` (23 файла: activity review-батчи,
full catalog, foundation, extensions, taxonomy, inventory, vocabulary и др.) и
загружает в справочные таблицы:

- ``activity_categories`` — из ``adult_category_taxonomy_source.v1.json``
  (13 source-категорий + 2 обязательные platform extensions) + категории,
  встречающиеся в карточках, но отсутствующие в таксономии;
- ``activity_catalog_items`` — системные записи (``owner_id = NULL``) из всех
  карточек ``cards`` (full_catalog / foundation / extensions / editorial);
- ``entities`` — базовые системные Entity (``owner_id = NULL, is_public = True``,
  ``content_status`` по манифесту) из тех же карточек;
- ``inventory_items`` — инвентарь из ``adult_inventory_source.v1.json``
  (``seed_ready=true``). Таблица user-scoped (``user_id`` NOT NULL, колонки
  ``is_system`` нет — R0-аудит), поэтому грузится только с ``--user-id``.

Idempotent: повторный запуск не создаёт дубликаты (upsert по уникальным ключам —
slug для категорий и Entity, name+category для каталога, name+user для
инвентаря). ``is_system`` в схеме не существует — системность выражается
``owner_id = NULL`` (см. ``app/api/catalog.py: is_system = owner_id is None``).

Гейт записи: по умолчанию печатает план (dry-run); запись — только с ``--apply``
(как ``tools/adult_catalog_import.py``, ADR-105).

Usage:
    python -m app.cli.seed_catalog                              # dry-run план
    python -m app.cli.seed_catalog --apply --database-url ...   # запись
    python -m app.cli.seed_catalog --apply --database-url ... --user-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_SEED_DIR = Path("data/seed")

# Манифесты, из которых берутся карточки активностей (ключ "cards")
CARD_MANIFESTS = (
    "adult_activity_full_catalog.v1.json",
    "adult_activity_foundation.v1.json",
    "adult_activity_extensions.v1.json",
    "adult_activity_editorial_candidates.v1.json",
)
CATEGORY_FILE = "adult_category_taxonomy_source.v1.json"
INVENTORY_FILE = "adult_inventory_source.v1.json"

# family → group_type для inventory_items (справочник group_type модели)
_FAMILY_GROUP_TYPE = {
    "body_device": "equipment",
    "restraint_hardware": "equipment",
    "sensory_equipment": "equipment",
    "electronic_concept": "electronics",
    "clothing_fetish": "wear",
    "care_supply": "care_cosmetics",
    "consumable_material": "general",
    "other": "general",
}


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _title_of(card: dict[str, Any]) -> str:
    t = card.get("title") or {}
    return t.get("ru") or t.get("en") or card.get("slug", "")


def _summary_of(card: dict[str, Any]) -> str | None:
    s = card.get("summary") or {}
    return s.get("ru") or s.get("en")


# ── Парсинг манифестов ────────────────────────────────────────────────


def parse_categories(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Категории из taxonomy + platform extensions."""
    out: list[dict[str, Any]] = []
    for idx, cat in enumerate(data.get("categories", [])):
        out.append(
            {
                "slug": cat["slug"],
                "title": cat.get("title_ru") or cat["slug"],
                "description": " / ".join(cat.get("source_labels", []) or [])[:500] or None,
                "sort_order": cat.get("order", idx),
            }
        )
    for ext in data.get("platform_extensions", []):
        out.append(
            {
                "slug": ext["slug"],
                "title": ext.get("reason", ext["slug"])[:200],
                "description": None,
                "sort_order": len(out),
            }
        )
    return out


def parse_cards(seed_dir: Path) -> list[dict[str, Any]]:
    """Собрать все карточки из CARD_MANIFESTS, дедуп по slug (первый выигрывает)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for name in CARD_MANIFESTS:
        path = seed_dir / name
        if not path.exists():
            continue
        data = _load_json(path)
        for card in data.get("cards", []):
            slug = card.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            out.append(card)
    return out


def parse_catalog_items(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Карточки → записи activity_catalog_items."""
    out: list[dict[str, Any]] = []
    for card in cards:
        tags = [card["content_kind"]] if card.get("content_kind") else None
        out.append(
            {
                "name": _title_of(card),
                "description": _summary_of(card),
                "category_slug": card.get("category"),
                "tags": tags,
                "domains": None,
            }
        )
    return out


def parse_entities(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Карточки → базовые системные Entity (owner_id=None, is_public=True)."""
    out: list[dict[str, Any]] = []
    for card in cards:
        slug = card["slug"]
        content_status = card.get("content_status") or card.get("status")
        if content_status not in ("reviewed", "approved", "draft"):
            content_status = "approved"  # owner decision (tools/adult_catalog_import.py)
        out.append(
            {
                "slug": slug,
                "real_name": _title_of(card),
                "short_title": _title_of(card)[:200],
                "category": card.get("category") or "other",
                "category_slug": card.get("category"),
                "tags": [card["content_kind"]] if card.get("content_kind") else None,
                "type": "one_time",
                "owner_id": None,
                "is_public": True,
                "params_schema": card.get("proposed_parameters") or card.get("parameters"),
                "risk_level": card.get("risk_level") or "not_assessed",
                "automation_allowed": bool(card.get("automation_allowed", False)),
                "content_status": content_status,
            }
        )
    return out


def parse_inventory_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Нормализованные предметы inventory source (seed_ready=true)."""
    out: list[dict[str, Any]] = []
    for item in data.get("items", []):
        if not item.get("seed_ready"):
            continue  # seed_ready=false — не готово к переносу
        family = item.get("family", "other")
        out.append(
            {
                "name": item.get("display_name_ru") or item.get("normalized_key") or item.get("item_id", ""),
                "description": item.get("source_refs") and "Источник: " + "; ".join(item["source_refs"]),
                "category": family,
                "group_type": _FAMILY_GROUP_TYPE.get(family, "general"),
            }
        )
    return out


# ── Запись (idempotent) ───────────────────────────────────────────────


async def _apply_plan(database_url: str, plan: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    # Импорт всех моделей — чтобы mapper registry разрешил FK (как в alembic/env.py).
    import app.models.catalog  # noqa: F401
    import app.models.category  # noqa: F401
    import app.models.entity  # noqa: F401 — ActivityCategory.entities → Entity
    import app.models.life  # noqa: F401
    import app.models.opt_in  # noqa: F401 — Entity.user_entity_opt_ins
    import app.models.user  # noqa: F401
    from app.models.catalog import ActivityCatalogItem
    from app.models.category import ActivityCategory
    from app.models.entity import Entity
    from app.models.life import InventoryItem

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    counts = {"categories": 0, "catalog": 0, "entities": 0, "inventory": 0, "skipped": 0}

    async with factory() as db:
        # Категории: upsert по slug (+ недостающие из карточек)
        slug_to_id: dict[str, Any] = {}
        for cat in plan["categories"]:
            existing = (
                await db.execute(select(ActivityCategory).where(ActivityCategory.slug == cat["slug"]).limit(1))
            ).scalar_one_or_none()
            if existing:
                existing.title = cat["title"]
                existing.description = cat["description"]
                existing.sort_order = cat["sort_order"]
                counts["skipped"] += 1
            else:
                db.add(ActivityCategory(**cat))
                counts["categories"] += 1
        await db.flush()
        result = await db.execute(select(ActivityCategory))
        for c in result.scalars().all():
            slug_to_id[c.slug] = c.id

        # Каталог: системные записи (owner_id NULL), без дубликатов по (name, category)
        for item in plan["catalog"]:
            category_id = slug_to_id.get(item["category_slug"])
            existing = (
                await db.execute(
                    select(ActivityCatalogItem.id)
                    .where(
                        ActivityCatalogItem.name == item["name"],
                        ActivityCatalogItem.owner_id.is_(None),
                        ActivityCatalogItem.category_id == category_id,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing:
                counts["skipped"] += 1
                continue
            db.add(
                ActivityCatalogItem(
                    name=item["name"],
                    description=item["description"],
                    category_id=category_id,
                    tags=item["tags"],
                    domains=item["domains"],
                    owner_id=None,
                    is_public=True,
                )
            )
            counts["catalog"] += 1

        # Системные Entity: без дубликатов по slug
        for ent in plan["entities"]:
            existing = (
                await db.execute(select(Entity.id).where(Entity.slug == ent["slug"]).limit(1))
            ).scalar_one_or_none()
            if existing:
                counts["skipped"] += 1
                continue
            category_id = slug_to_id.get(ent["category_slug"])
            db.add(
                Entity(
                    slug=ent["slug"],
                    real_name=ent["real_name"],
                    short_title=ent["short_title"],
                    category=ent["category"],
                    category_id=category_id,
                    tags=ent["tags"],
                    type=ent["type"],
                    owner_id=None,
                    is_public=True,
                    params_schema=ent["params_schema"],
                    risk_level=ent["risk_level"],
                    automation_allowed=ent["automation_allowed"],
                    content_status=ent["content_status"],
                )
            )
            counts["entities"] += 1

        # Инвентарь: только для указанного пользователя (таблица user-scoped)
        if user_id and plan["inventory"]:
            from uuid import UUID as _UUID

            uid = _UUID(user_id)
            for item in plan["inventory"]:
                existing = (
                    await db.execute(
                        select(InventoryItem.id)
                        .where(InventoryItem.user_id == uid, InventoryItem.name == item["name"])
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if existing:
                    counts["skipped"] += 1
                    continue
                db.add(
                    InventoryItem(
                        user_id=uid,
                        category=item["category"],
                        group_type=item["group_type"],
                        name=item["name"],
                        description=item["description"],
                        quantity=1,
                        quantity_needed=1,
                        is_shopping_list=False,
                        status="need",
                        inventory_status="available",
                    )
                )
                counts["inventory"] += 1

        await db.commit()
    await engine.dispose()
    return counts


def _render_plan(plan: dict[str, Any], user_id: str | None) -> str:
    lines = [
        "Каталог seed — dry-run план",
        f"  файлов прочитано:   {plan['files']}",
        f"  категории:          {len(plan['categories'])}",
        f"  записи каталога:    {len(plan['catalog'])}",
        f"  системные Entity:   {len(plan['entities'])}",
        f"  инвентарь (готовые):{len(plan['inventory'])}",
        f"  user_id для инвентаря: {user_id or '— (не указан, инвентарь пропущен)'}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сидер каталога из data/seed (R2.1)")
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--database-url", default=None, help="PostgreSQL connection string")
    parser.add_argument("--apply", action="store_true", help="записать в БД (по умолчанию dry-run)")
    parser.add_argument("--user-id", default=None, help="user_id для загрузки инвентаря")
    args = parser.parse_args(argv)

    seed_dir = args.seed_dir
    if not seed_dir.is_dir():
        print(f"ERROR: seed dir not found: {seed_dir}", file=sys.stderr)
        return 1

    # Читаем все JSON-манифесты в data/seed/
    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(seed_dir.glob("*.json")):
        try:
            manifests[path.name] = _load_json(path)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"ERROR: cannot parse {path.name}: {exc}", file=sys.stderr)
            return 1

    categories: list[dict[str, Any]] = []
    if CATEGORY_FILE in manifests:
        categories = parse_categories(manifests[CATEGORY_FILE])

    cards = parse_cards(seed_dir)
    catalog = parse_catalog_items(cards)
    entities = parse_entities(cards)

    inventory: list[dict[str, Any]] = []
    if INVENTORY_FILE in manifests:
        inventory = parse_inventory_items(manifests[INVENTORY_FILE])

    plan = {
        "files": len(manifests),
        "categories": categories,
        "catalog": catalog,
        "entities": entities,
        "inventory": inventory,
    }

    if not args.apply:
        print(_render_plan(plan, args.user_id))
        print("\nDry-run. Передайте --apply --database-url ... для записи (ADR-105).")
        return 0

    database_url = args.database_url
    if not database_url:
        from app.config import settings

        database_url = settings.database_url
    if not database_url:
        print("ERROR: --database-url required (или настройте DATABASE_URL в .env)", file=sys.stderr)
        return 1

    counts = asyncio.run(_apply_plan(database_url, plan, args.user_id))
    print(
        f"imported: categories={counts['categories']} catalog={counts['catalog']} "
        f"entities={counts['entities']} inventory={counts['inventory']} skipped={counts['skipped']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
