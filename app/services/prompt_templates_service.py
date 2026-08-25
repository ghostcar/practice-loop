"""Prompt Templates Service — business logic extracted from app.api.prompt_templates.

Covers: serialization, page context, CRUD, schema validation, LLM generation,
usage tracking, library integration.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.pipeline.generate import get_active_llm_config
from app.llm.pipeline.templates import extract_template_vars, generate_from_template
from app.llm.prompt_library import get_prompt, list_prompts, prompt_categories, render_system_prompt
from app.models.prompt_template import PromptTemplate

# ── Constants ──
MAX_PROMPT_LEN = 20_000
MAX_NAME_LEN = 200


# ═══════════════════════════════════════════════════════════════════════════
# Serializers
# ═══════════════════════════════════════════════════════════════════════════


def serialize(t: PromptTemplate) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "description": t.description,
        "template_type": t.template_type,
        "system_prompt": t.system_prompt,
        "params_schema": t.params_schema,
        "is_active": t.is_active,
        "source_key": t.source_key,
        "usage_count": t.usage_count,
        "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
        "vars": extract_template_vars(t.system_prompt),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Schema validation
# ═══════════════════════════════════════════════════════════════════════════


def validate_schema_json(raw: str) -> dict | list | None:
    """Parse and sanitize the params_schema JSON (ADR-041 format)."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"params_schema is not valid JSON: {e}") from e
    if not isinstance(parsed, dict | list):
        raise ValueError("params_schema must be a JSON object or array")
    from app.params import normalize_schema

    try:
        normalize_schema(parsed)
    except ValueError as e:
        raise ValueError(f"Invalid params_schema: {e}") from e
    return parsed


# ═══════════════════════════════════════════════════════════════════════════
# Page contexts
# ═══════════════════════════════════════════════════════════════════════════


def get_library_context(locale: str, t) -> dict:
    """Build context for /llm/prompts (system library page)."""
    prompts = []
    for p in list_prompts():
        prompts.append(
            {
                "key": p.key,
                "category": p.category,
                "title": t.get(p.title_key, p.key),
                "description": t.get(p.description_key, ""),
                "preview": render_system_prompt(p, locale=locale)[:400],
                "vars": list(p.format_vars),
            }
        )
    return {
        "prompts": prompts,
        "categories": prompt_categories(),
    }


async def get_templates_page_context(db: AsyncSession, user) -> dict:
    """Build context for /llm/templates (user's private templates list)."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.user_id == user.id).order_by(PromptTemplate.created_at.desc())
    )
    templates_list = [serialize(pt) for pt in result.scalars().all()]
    llm_config = await get_active_llm_config(db, user.id)
    return {
        "templates": templates_list,
        "has_llm_config": llm_config is not None,
        "library_prompts": [{"key": p.key, "title": p.title_key, "category": p.category} for p in list_prompts()],
    }


def get_user_prompt_library_context(t) -> dict:
    """Build context for /prompts/library (categorized prompt library hub)."""
    # This needs a db session — handled at route level
    # Return just the structure hint; caller does the query
    return {}


async def get_user_prompt_library_items(db: AsyncSession) -> dict:
    """Query system + user prompts for /prompts/library."""
    from app.models.prompt_library import PromptLibraryItem

    items = (await db.execute(select(PromptLibraryItem).order_by(PromptLibraryItem.key))).scalars().all()
    system_prompts = [i for i in items if i.library_type == "system"]
    user_prompts = [i for i in items if i.library_type == "user"]
    return {
        "system_prompts": system_prompts,
        "user_prompts": user_prompts,
    }


async def get_template_detail_context(db: AsyncSession, user, template_id: uuid.UUID) -> dict:
    """Build context for /llm/templates/{id} (detail/edit page)."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id, PromptTemplate.user_id == user.id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise ValueError("Template not found")

    data = serialize(template)
    schema_json = json.dumps(template.params_schema, ensure_ascii=False, indent=2) if template.params_schema else ""
    data["params_schema_json"] = schema_json
    data["vars"] = extract_template_vars(template.system_prompt)
    llm_config = await get_active_llm_config(db, user.id)
    return {
        "template": data,
        "has_llm_config": llm_config is not None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════════════════════


async def create_template(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    description: str = "",
    template_type: str = "text",
    system_prompt: str,
    params_schema: str = "",
    source_key: str = "",
) -> PromptTemplate:
    """Create a private prompt template."""
    name = name.strip()[:MAX_NAME_LEN]
    if not name:
        raise ValueError("Template name is required")
    if len(system_prompt) > MAX_PROMPT_LEN:
        raise ValueError("System prompt is too long")
    ttype = template_type.strip().lower()
    if ttype not in ("text", "task"):
        ttype = "text"

    schema = validate_schema_json(params_schema)
    template = PromptTemplate(
        user_id=user_id,
        name=name,
        description=(description or "").strip()[:2000] or None,
        template_type=ttype,
        system_prompt=system_prompt,
        params_schema=schema,
        source_key=(source_key or "").strip()[:50] or None,
    )
    db.add(template)
    await db.flush()
    return template


async def create_template_from_library(
    db: AsyncSession,
    user_id: uuid.UUID,
    key: str,
    *,
    name: str = "",
    template_type: str = "text",
    locale: str = "en",
    t=None,
) -> PromptTemplate:
    """Create a private template from a library prompt."""
    prompt_def = get_prompt(key)
    if prompt_def is None:
        raise ValueError(f"Unknown library prompt: {key}")

    system_prompt = render_system_prompt(prompt_def, locale=locale)
    default_name = name.strip() or (t.get(prompt_def.title_key, key) if t else key)

    template = PromptTemplate(
        user_id=user_id,
        name=default_name[:MAX_NAME_LEN],
        description=(t.get(prompt_def.description_key, "") if t else ""),
        template_type=template_type,
        system_prompt=system_prompt,
        source_key=prompt_def.key,
    )
    db.add(template)
    await db.flush()
    return template


async def update_template(
    db: AsyncSession,
    user_id: uuid.UUID,
    template_id: uuid.UUID,
    *,
    name: str = "",
    description: str = "",
    template_type: str = "text",
    system_prompt: str = "",
    params_schema: str = "",
    is_active: str = "",
) -> PromptTemplate:
    """Update a private prompt template."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id, PromptTemplate.user_id == user_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise ValueError("Template not found")

    template.name = (name or template.name).strip()[:MAX_NAME_LEN]
    template.description = (description or "").strip()[:2000] or None
    ttype = template_type.strip().lower()
    if ttype in ("text", "task"):
        template.template_type = ttype
    if system_prompt and len(system_prompt) <= MAX_PROMPT_LEN:
        template.system_prompt = system_prompt
    template.params_schema = validate_schema_json(params_schema)
    template.is_active = is_active.strip().lower() in {"1", "on", "true", "yes"}
    db.add(template)
    await db.flush()
    return template


async def delete_template(db: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID) -> None:
    """Delete a private prompt template."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id, PromptTemplate.user_id == user_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise ValueError("Template not found")
    await db.delete(template)


# ═══════════════════════════════════════════════════════════════════════════
# LLM Generation
# ═══════════════════════════════════════════════════════════════════════════


async def execute_generation(
    db: AsyncSession,
    user_id: uuid.UUID,
    template_id: uuid.UUID,
    locale: str,
    params: dict | None = None,
) -> dict:
    """Run LLM generation from a template, track usage, return outcome."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id, PromptTemplate.user_id == user_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise ValueError("Template not found")

    llm_config = await get_active_llm_config(db, user_id)
    if llm_config is None:
        raise ValueError("No active LLM provider configured")

    try:
        outcome = await generate_from_template(
            db=db,
            user_id=user_id,
            llm_config=llm_config,
            template=template,
            params=params or {},
            locale=locale,
        )
    except ValueError:
        raise

    # Track usage + bump counter
    usage = outcome.get("usage", {})
    llm_config.total_tokens += usage.get("total_tokens", 0)
    llm_config.total_cost += usage.get("cost", 0.0)
    template.usage_count += 1
    template.last_used_at = datetime.now(UTC)
    db.add(llm_config)
    db.add(template)
    await db.flush()

    return outcome


async def list_templates(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """List all user templates as dicts (JSON API)."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.user_id == user_id).order_by(PromptTemplate.created_at.desc())
    )
    return [serialize(pt) for pt in result.scalars().all()]
