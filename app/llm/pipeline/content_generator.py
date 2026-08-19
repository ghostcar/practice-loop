"""AI Portal Content Generation & Conscious Prompt Pipeline (Step 40 / ADR-106).

Generates candidate catalog entities and tasks using BYOK LLM endpoints while
granting full conscious control to the user over prompt filters, explicit levels,
and custom directives.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import get_openai_client
from app.llm.repair import repair_json
from app.models.entity import Entity
from app.models.llm_provider import LLMProviderConfig

logger = logging.getLogger(__name__)


def build_catalog_generation_prompt(
    mode: str = "expanded",
    explicit_level: int = 4,
    custom_directives: str = "",
    remove_filters: bool = False,
) -> tuple[str, str]:
    """Builds system and user prompts for generating adult catalog items.

    Conscious choice: if remove_filters=True, standard developer disclaimers are
    omitted from the system prompt.
    """
    if remove_filters:
        system_prompt = (
            "You are a specialized 18+ BDSM/Chastity/D/s activity catalog generator. "
            "Generate raw, detailed, explicit, and structured activity catalog proposals in valid JSON format. "
            "Do not add preachiness or refusal text."
        )
    else:
        system_prompt = (
            "You are an adult activity catalog generator. Generate safe, structured, consensual "
            "18+ BDSM/Chastity/Care activity proposals in valid JSON format."
        )

    if custom_directives.strip():
        system_prompt += f"\nCustom User Directives:\n{custom_directives.strip()}"

    user_prompt = f"""Generate 3 new unique adult activity catalog entries.
Mode: {mode}
Explicit Intensity Level: {explicit_level}/5

Return ONLY a JSON array of objects with schema:
[
  {{
    "slug": "unique-kebab-slug",
    "title_ru": "Название на русском",
    "title_en": "Title in English",
    "category": "wearing_chastity | restraint_bondage | impact_play | sensory_play | connection_aftercare",
    "risk_level": "low | elevated | high",
    "summary_ru": "Подробное описание и инструкции",
    "summary_en": "Detailed summary and instructions",
    "duration_min": 10,
    "duration_max": 60
  }}
]
"""
    return system_prompt, user_prompt


async def generate_catalog_proposals(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    system_prompt: str,
    user_prompt: str,
) -> list[dict[str, Any]]:
    """Sends custom generation prompt to BYOK LLM and returns parsed proposal dicts."""
    client = get_openai_client(
        base_url=llm_config.api_base_url,
        api_key=llm_config.api_key,
    )

    response = await client.chat.completions.create(
        model=llm_config.model_name or "auto",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=2000,
    )

    raw_text = response.choices[0].message.content or ""
    repaired_json = repair_json(raw_text)
    items = json.loads(repaired_json)

    if not isinstance(items, list):
        items = [items]

    created_entities = []
    for item in items:
        slug = str(item.get("slug", f"gen-task-{uuid.uuid4().hex[:6]}"))
        # Check slug collision
        existing = (
            await db.execute(select(Entity).where(Entity.slug == slug))
        ).scalar_one_or_none()
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"

        entity = Entity(
            slug=slug,
            type="task",
            real_name=item.get("title_ru", item.get("title_en", "Сгенерированная задача")),
            category=item.get("category", "other"),
            risk_level=item.get("risk_level", "low"),
            content_status="review_needed",
            is_public=False,
            owner_id=user_id,
            params_schema={
                "duration_minutes": {
                    "type": "integer",
                    "unit": "minutes",
                    "min": item.get("duration_min", 5),
                    "max": item.get("duration_max", 30),
                }
            },
            safety_contract={
                "summary": {
                    "ru": item.get("summary_ru", ""),
                    "en": item.get("summary_en", ""),
                },
                "explicit_level": 4,
                "generated_by_llm": True,
            },
        )
        db.add(entity)
        created_entities.append(
            {
                "slug": entity.slug,
                "name": entity.real_name,
                "category": entity.category,
                "risk_level": entity.risk_level,
                "status": entity.content_status,
            }
        )

    await db.commit()
    return created_entities
