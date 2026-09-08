"""OpenAI-compatible LLM client — configured from LLMProviderConfig (BYOK)."""

import logging
import time
import uuid
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import decrypt_api_key
from app.models.llm_config import LLMProviderConfig

logger = logging.getLogger(__name__)

# Section/purpose of the current call, set by pipeline wrappers so the call
# log knows who asked. Kept as module state because call_llm's signature is
# frozen across many call-sites; wrappers always set it right before calling.
_last_call_meta: dict[str, str | None] = {"section": None, "purpose": None}


def set_call_meta(section: str | None = None, purpose: str | None = None) -> None:
    """Attach section/purpose metadata to the next call_llm invocation."""
    _last_call_meta["section"] = (section or "")[:50] or None
    _last_call_meta["purpose"] = (purpose or "")[:60] or None


# Vision (image parts) support — Step 7, ADR-075.
# Omniroute routes image_url parts to vision-capable models (verified with
# openrouter/openai/gpt-4o-mini, cheap). Images are passed as data URLs; the
# caller is responsible for loading them from the private upload store.
MAX_IMAGE_PARTS = 4

# Approximate cost per 1K tokens for common models (USD)
# Used when the provider doesn't return cost data
DEFAULT_COST_PER_1K: dict[str, tuple[float, float]] = {
    # (prompt, completion)
    "gpt-4o": (0.0025, 0.010),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4": (0.03, 0.06),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "llama": (0.0, 0.0),  # free tier
    "mixtral": (0.0, 0.0),
    "gemini": (0.0, 0.0),  # free tier
}


def _estimate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost based on model name heuristics."""
    model_lower = model_name.lower()
    for key, (prompt_rate, comp_rate) in DEFAULT_COST_PER_1K.items():
        if key in model_lower:
            return (prompt_tokens / 1000) * prompt_rate + (completion_tokens / 1000) * comp_rate


def get_openai_client(base_url: str, api_key: str | None = None) -> AsyncOpenAI:
    """Helper to instantiate an AsyncOpenAI client for pipeline calls."""
    key = api_key or "not-needed"
    return AsyncOpenAI(base_url=base_url, api_key=key, timeout=60.0)


async def list_llm_models(base_url: str, api_key: str | None) -> list[str]:
    """Return model IDs advertised by an OpenAI-compatible provider."""
    client = get_openai_client(base_url.strip().rstrip("/"), api_key)
    try:
        models = await client.models.list()
        return sorted({item.id for item in models.data})
    except Exception as exc:
        raise RuntimeError("LLM connection check failed") from exc
    finally:
        await client.close()


async def check_llm_connection(base_url: str, api_key: str | None, model_name: str) -> None:
    """Verify an OpenAI-compatible provider before storing its credentials."""
    available = await list_llm_models(base_url, api_key)
    if available and model_name not in available:
        raise ValueError(f"Model '{model_name}' is not available")


async def call_llm(
    config: LLMProviderConfig,
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None = None,
    json_mode: bool = True,
    images: list[str] | None = None,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Call the LLM via OpenAI-compatible API. Returns {'content': ..., 'usage': ...}.

    ``images`` — data URLs (data:image/...;base64,...) appended to the user
    message as image parts (vision, ADR-075). Max MAX_IMAGE_PARTS images.

    When ``db`` + ``user_id`` are provided, the call is recorded into
    ``llm_call_logs`` (ADR-191) — success or failure, with latency and a
    truncated error message. Errors still propagate to the caller.
    """
    started = time.monotonic()
    section = _last_call_meta.get("section")
    purpose = _last_call_meta.get("purpose")
    _last_call_meta["section"] = None
    _last_call_meta["purpose"] = None

    api_key = decrypt_api_key(config.api_key_encrypted) if config.api_key_encrypted else "not-needed"

    client = AsyncOpenAI(
        base_url=config.api_base_url,
        api_key=api_key,
        timeout=60.0,
    )

    user_content: Any = user_message
    if images:
        parts: list[dict[str, Any]] = [{"type": "text", "text": user_message}]
        for url in images[:MAX_IMAGE_PARTS]:
            parts.append({"type": "image_url", "image_url": {"url": url}})
        user_content = parts

    kwargs: dict[str, Any] = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    try:
        response = await client.chat.completions.create(**kwargs)
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        if db is not None and user_id is not None:
            await _log_call(
                db,
                user_id=user_id,
                config=config,
                capability="vision" if images else "text",
                section=section,
                purpose=purpose,
                status="error",
                error_message=str(exc)[:1000],
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0.0},
                duration_ms=duration_ms,
            )
        raise

    message = response.choices[0].message
    content = message.content or ""

    usage = {
        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
        "total_tokens": response.usage.total_tokens if response.usage else 0,
    }

    # Estimate cost if usage > 0
    cost = _estimate_cost(
        config.model_name,
        usage["prompt_tokens"],
        usage["completion_tokens"],
    )
    usage["cost"] = cost

    duration_ms = int((time.monotonic() - started) * 1000)
    if db is not None and user_id is not None:
        await _log_call(
            db,
            user_id=user_id,
            config=config,
            capability="vision" if images else "text",
            section=section,
            purpose=purpose,
            status="ok",
            error_message=None,
            usage=usage,
            duration_ms=duration_ms,
        )

    return {
        "content": content,
        "usage": usage,
        "tool_calls": [
            {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            for tc in (message.tool_calls or [])
        ],
    }


async def _log_call(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    config: LLMProviderConfig,
    capability: str,
    section: str | None,
    purpose: str | None,
    status: str,
    error_message: str | None,
    usage: dict[str, Any],
    duration_ms: int,
) -> None:
    """Persist one LLM invocation into llm_call_logs (best-effort, ADR-191)."""
    from decimal import Decimal

    from app.models.llm_config import LLMCallLog

    try:
        cost = usage.get("cost") or 0.0
        db.add(
            LLMCallLog(
                user_id=user_id,
                config_id=getattr(config, "id", None),
                provider_name=config.provider_name,
                model_name=config.model_name,
                capability=capability,
                section=section,
                purpose=purpose,
                status=status,
                error_message=error_message,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
                cost=Decimal(str(cost)),
                duration_ms=duration_ms,
            )
        )
        await db.flush()
    except Exception:  # noqa: BLE001 — лог не должен ломать основной вызов
        logger.warning("Failed to write llm_call_log", exc_info=True)
