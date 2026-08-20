"""Pipeline for Manual LLM Prompt Export & Response Import Hub ("Внешняя ИИ-модель").

Supports cross-domain prompt generation and post-import reference hydration.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.repair import parse_llm_json
from app.models.catalog import ActivityCatalogItem
from app.models.life import InventoryItem
from app.models.task_location import TaskLocation

logger = logging.getLogger(__name__)

DOMAIN_LABELS = {
    "tracker": "Задачи и Активности",
    "timer": "Таймеры и Удержания",
    "care": "Протоколы Ухода",
    "training": "Тренировки",
    "diets": "Планы Питания",
    "journal": "Записи Дневника",
}


async def build_exportable_cross_domain_prompt(
    db: AsyncSession,
    user_id: uuid.UUID,
    domains: list[str],
    locale: str = "ru",
) -> str:
    """Builds a lightweight cross-domain master prompt for external LLM generation."""
    if not domains:
        domains = ["tracker"]

    # Fetch catalog items available for user or system
    catalog_query = select(ActivityCatalogItem).where(
        ActivityCatalogItem.owner_id.is_(None) | (ActivityCatalogItem.owner_id == user_id)
    )
    items = (await db.execute(catalog_query)).scalars().all()

    formatted_items = []
    for it in items[:30]:
        formatted_items.append(
            f"- [ID: {it.id}] {it.name}" + (f" ({it.description[:60]}...)" if it.description else "")
        )

    items_text = "\n".join(formatted_items) if formatted_items else "- [Системные активности]"

    domain_titles = [DOMAIN_LABELS.get(d, d) for d in domains]
    domains_str = ", ".join(domain_titles)

    prompt = f"""Ты — ИИ-ассистент трекера актов и согласий PracticeLoop.
Сгенерируй согласованный план активностей по следующим сферам: {domains_str}.

Допустимый настраиваемый каталог сущностей:
{items_text}

Инструкция для внешней модели:
1. Выбери 1-5 уместных активностей с разумными параметрами (длительность в мин., интенсивность 1-5, примечания).
2. Верни ответ СТРОГО в формате JSON без вводного текста.

Формат ответа JSON:
{{
  "title": "Сквозной план от Внешней ИИ",
  "reasoning": "Обоснование подбора...",
  "items": [
    {{
      "domain": "tracker",
      "entity_id": "<uuid_или_null>",
      "title": "Название активности",
      "duration_minutes": 20,
      "intensity": 3,
      "suggested_inventory": "Название требуемого инвентаря (обобщенно)",
      "suggested_location": "Локация (обобщенно)",
      "notes": "Примечания по выполнению"
    }}
  ]
}}
"""
    return prompt.strip()


def parse_external_llm_response(raw_text: str) -> dict[str, Any]:
    """Parses raw text/json pasted from an external LLM using json_repair."""
    return parse_llm_json(raw_text)


async def get_user_reference_catalogs(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict[str, list[dict[str, str]]]:
    """Fetches user inventory and locations for reference mapping UI dropdowns."""
    inventory_query = select(InventoryItem).where(InventoryItem.user_id == user_id)
    inventory_items = (await db.execute(inventory_query)).scalars().all()

    location_query = select(TaskLocation).where(TaskLocation.owner_id.is_(None) | (TaskLocation.owner_id == user_id))
    locations = (await db.execute(location_query)).scalars().all()

    return {
        "inventory": [{"id": str(i.id), "name": i.name} for i in inventory_items],
        "locations": [{"id": str(loc.id), "name": loc.title_ru or loc.title_en or loc.slug} for loc in locations],
    }
