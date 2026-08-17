"""Template-based LLM generation (ADR-070, Step 6).

``generate_from_template`` — параметрическая генерация по пользовательскому
промпт-шаблону (``PromptTemplate``):

- ``text`` — системный промпт = шаблон (переменные ``{{var}}`` подставляются
  из входных параметров), ответ — свободный текст (JSON mode по желанию).
- ``task`` — как ``generate_task``, но с кастомным системным промптом из
  шаблона: LLM выбирает задачу из допустимого (opt-in) набора, ответ
  валидируется (allowed set + params schema) и сохраняется в ActivityLog.

Переменные шаблона описываются в ``PromptTemplate.params_schema`` в формате
ADR-041 и валидируются через ``app.params.validate_params`` (без eval).
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import client, context_builder, validator
from app.llm.context_builder import (
    filter_automation_eligible,
    format_context_abstract,
    format_context_for_prompt,
)
from app.llm.mode import llm_mode_hint
from app.llm.pipeline.generate import (
    MAX_RETRIES,
    _generate_task_title,
    _resolve_raw_response,
)
from app.llm.repair import JsonRepairError, parse_llm_json
from app.llm.tools import TOOLS
from app.llm.validator import (
    validate_llm_response,
    validate_params_against_schema,
)
from app.models.activity_log import ActivityLog
from app.models.llm_config import LLMProviderConfig
from app.models.prompt_template import PromptTemplate

logger = logging.getLogger(__name__)

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def extract_template_vars(system_prompt: str) -> list[str]:
    """List of ``{{var}}`` placeholders in a template system prompt."""
    return list(dict.fromkeys(_VAR_RE.findall(system_prompt)))


def render_template_prompt(system_prompt: str, params: dict | None) -> str:
    """Substitute ``{{var}}`` placeholders with values from params.

    Missing variables are replaced with an empty string so the prompt stays
    well-formed; unknown keys in params are ignored (prompt is the contract).
    """
    values = params or {}
    rendered = system_prompt

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        val = values.get(key)
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return _VAR_RE.sub(_sub, rendered)


async def generate_from_template(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    template: PromptTemplate,
    params: dict | None = None,
    locale: str = "en",
    session_id: uuid.UUID | None = None,
    llm_mode: str | None = None,
) -> dict:
    """Run a prompt template. Returns a dict with the generated result.

    - ``text`` → {"type": "text", "content": str, "usage": {...}}
    - ``task`` → {"type": "task", "activity_log_id": uuid, "entity_id": ...,
                  "title": ..., "params": {...}, "usage": {...}}
    """
    params = params or {}

    # ── Validate variables against the template's params_schema (ADR-041) ──
    from app.params import validate_params

    schema_errors = validate_params(template.params_schema, params)
    if schema_errors:
        raise ValueError(f"Template params invalid: {'; '.join(schema_errors)}")

    if template.template_type == "task":
        return await _generate_task_from_template(
            db, user_id, llm_config, template, params, locale, session_id, llm_mode
        )

    return await _generate_text_from_template(llm_config, template, params, locale, llm_mode)


async def _generate_text_from_template(
    llm_config: LLMProviderConfig,
    template: PromptTemplate,
    params: dict,
    locale: str,
    llm_mode: str | None = None,
) -> dict:
    """Free-text generation: system = rendered template, user = params context."""
    system_prompt = render_template_prompt(template.system_prompt, params) + llm_mode_hint(llm_mode)
    user_message = (
        f"Parameters:\n{json.dumps(params, ensure_ascii=False, default=str)}\n\n"
        f"Follow the instructions in the system prompt. Respond in {locale}."
    )

    raw_response = ""
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0.0}
    content = ""

    for attempt in range(MAX_RETRIES):
        is_last = attempt == MAX_RETRIES - 1
        try:
            result = await client.call_llm(
                config=llm_config,
                system_prompt=system_prompt,
                user_message=user_message,
                json_mode=False,
            )
            raw_response = result["content"]
            usage = result["usage"]
            content = raw_response
            break
        except ValueError as e:  # pragma: no cover - defensive
            logger.warning(f"Template LLM attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if is_last:
                raise JsonRepairError(f"Failed to generate after {MAX_RETRIES} attempts: {e}") from e

    # Usage is applied to the provider config by the caller (has the db session).
    return {"type": "text", "content": content, "usage": usage, "raw_response": raw_response}


async def _generate_task_from_template(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    template: PromptTemplate,
    params: dict,
    locale: str,
    session_id: uuid.UUID | None,
    llm_mode: str | None = None,
) -> dict:
    """Task selection with a custom system prompt (like generate_task)."""
    context = await context_builder.build_context(db, user_id, session_id=session_id, locale=locale)
    context["allowed_entities"] = filter_automation_eligible(context.get("allowed_entities", []))
    allowed_ids = validator.get_allowed_ids(context)

    is_abstract = getattr(llm_config, "llm_mode", "full") == "abstract"
    context_text = format_context_abstract(context) if is_abstract else format_context_for_prompt(context)

    system_prompt = render_template_prompt(template.system_prompt, params) + llm_mode_hint(llm_mode)
    user_message = f"Context:\n{context_text}\n\n"
    if params:
        user_message += f"Template parameters: {json.dumps(params, ensure_ascii=False, default=str)}\n\n"
    user_message += "Suggest a task from the allowed entities list."

    raw_response = ""
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0.0}
    parsed: dict = {}

    for attempt in range(MAX_RETRIES):
        is_last = attempt == MAX_RETRIES - 1
        try:
            result = await client.call_llm(
                config=llm_config,
                system_prompt=system_prompt,
                user_message=user_message,
                tools=TOOLS,
                json_mode=True,
            )
            raw_response = result["content"]
            usage = result["usage"]
            parsed = parse_llm_json(raw_response, is_last_attempt=is_last)
            if result.get("tool_calls"):
                for tc in result["tool_calls"]:
                    if tc["name"] == "save_activity_log":
                        parsed = json.loads(tc["arguments"])
                        break
            if parsed:
                break
        except ValueError as e:
            logger.warning(f"Template task attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
        except JsonRepairError:
            raise
    else:
        raise JsonRepairError(f"Failed to parse LLM JSON after {MAX_RETRIES} attempts.")

    entity_id = parsed.get("entity_id")
    entity_name = parsed.get("entity_name")
    task_params = parsed.get("params")

    if not entity_id or not entity_name:
        raise ValueError("LLM response missing entity_id or entity_name")

    validation_errors = validate_llm_response(parsed, allowed_ids)
    if validation_errors:
        raise ValueError(f"LLM response validation failed: {'; '.join(validation_errors)}")

    entities_by_id = {e["id"]: e for e in context.get("allowed_entities", [])}
    schema = entities_by_id.get(str(entity_id), {}).get("params_schema") if entity_id else None
    schema_errors = validate_params_against_schema(task_params, schema)
    if schema_errors:
        raise ValueError(f"LLM params fail entity schema: {'; '.join(schema_errors)}")

    canonical = entities_by_id.get(str(entity_id), {})
    entity_name = canonical.get("name") or entity_name

    raw_to_store, raw_expires = _resolve_raw_response(llm_config, raw_response)
    auto_title = _generate_task_title(
        entity_name=entity_name,
        params=task_params,
        schema=canonical.get("params_schema"),
        template=canonical.get("task_template"),
        locale=locale,
    )
    log = ActivityLog(
        user_id=user_id,
        session_id=session_id,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        status="planned",
        title_override=auto_title if auto_title != entity_name else None,
        user_prompt=f"Template: {template.name}",
        raw_llm_response=raw_to_store,
        raw_response_expires_at=raw_expires,
        cleaned_response=parsed,
        selected_entity_name=entity_name,
        selected_params=task_params,
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
        cost=usage["cost"],
    )
    db.add(log)
    await db.flush()

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()

    return {
        "type": "task",
        "activity_log_id": log.id,
        "entity_id": str(entity_id),
        "entity_name": entity_name,
        "title": auto_title,
        "params": task_params,
        "usage": usage,
    }
