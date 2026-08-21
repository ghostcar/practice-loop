"""CLI-сидер каталога (R2.1, REFACTOR_ROADMAP_V2.md).

Парсит JSON-манифесты из ``data/seed/`` и загружает их в справочные таблицы:

- ``adult_category_taxonomy_source.v1.json`` → ``activity_categories``;
- ``adult_activity_full_catalog.v1.json``   → ``activity_catalog_items``;
- ``adult_inventory_source.v1.json``        → ``inventory_items``.

Idempotent: повторный запуск не создаёт дубликаты (upsert по уникальным ключам —
slug для категорий, name+category для каталога, name+user для инвентаря).

``inventory_items`` — пользовательская таблица (``user_id`` NOT NULL, колонки
``is_system`` нет — см. R0-аудит, dead/inventory scoping). Поэтому инвентарь
загружается только при передаче ``--user-id``; без него секция пропускается с
предупреждением. Категории и каталог — системные (``owner_id = NULL``).

Гейт записи: по умолчанию скрипт печатает план (dry-run); фактическая запись —
только с ``--apply`` (как ``tools/adult_catalog_import.py``, ADR-105).

Usage:
    python -m app.cli.seed_catalog                              # dry-run план
    python -m app.cli.seed_catalog --apply --database-url ...   # запись каталога
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
CATEGORY_FILE = "adult_category_taxonomy_source.v1.json"
CATALOG_FILE = "adult_activity_full_catalog.v1.json"
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


# ── Парсинг манифестов ────────────────────────────────────────────────


def parse_categories(data: dict[str, Any]) -> list[dict[str, Any]]:
    """13 source-категорий + 2 обязательные platform extensions."""
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


def parse_catalog_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Карточки full catalog → записи activity_catalog_items."""
    out: list[dict[str, Any]] = []
    for card in data.get("cards", []):
        title = (card.get("title") or {}).get("ru") or (card.get("title") or {}).get("en") or card.get("slug", "")
        summary = (card.get("summary") or {}).get("ru") or (card.get("summary") or {}).get("en")
        tags = [card["content_kind"]] if card.get("content_kind") else None
        out.append(
            {
                "name": title,
                "description": summary,
                "category_slug": card.get("category"),
                "tags": tags,
                "domains": None,
            }
        )
    return out


def parse_inventory_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Нормализованные предметы inventory source."""
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
    import app.models.life  # noqa: F401
    import app.models.user  # noqa: F401
    import app.models.entity  # noqa: F401 — ActivityCategory.entities → Entity
    import app.models.opt_in  # noqa: F401 — Entity.user_entity_opt_ins
    from app.models.catalog import ActivityCatalogItem
    from app.models.category import ActivityCategory
    from app.models.life import InventoryItem

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    counts = {"categories": 0, "catalog": 0, "inventory": 0, "skipped": 0}

    async with factory() as db:
        # Категории: upsert по slug
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
        f"  категории:          {len(plan['categories'])}",
        f"  записи каталога:    {len(plan['catalog'])}",
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
    category_file = seed_dir / CATEGORY_FILE
    catalog_file = seed_dir / CATALOG_FILE
    inventory_file = seed_dir / INVENTORY_FILE
    missing = [p for p in (category_file, catalog_file, inventory_file) if not p.exists()]
    if missing:
        for p in missing:
            print(f"ERROR: manifest missing: {p}", file=sys.stderr)
        return 1

    categories = parse_categories(_load_json(category_file))
    catalog = parse_catalog_items(_load_json(catalog_file))
    inventory = parse_inventory_items(_load_json(inventory_file))
    plan = {"categories": categories, "catalog": catalog, "inventory": inventory}

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
        f"inventory={counts['inventory']} skipped={counts['skipped']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
