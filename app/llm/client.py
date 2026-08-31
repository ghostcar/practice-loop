"""OpenAI-compatible LLM client — configured from LLMProviderConfig (BYOK)."""

from typing import Any

from openai import AsyncOpenAI

from app.encryption import decrypt_api_key
from app.models.llm_config import LLMProviderConfig

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
) -> dict[str, Any]:
    """Call the LLM via OpenAI-compatible API. Returns {'content': ..., 'usage': ...}.

    ``images`` — data URLs (data:image/...;base64,...) appended to the user
    message as image parts (vision, ADR-075). Max MAX_IMAGE_PARTS images.
    """

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

    response = await client.chat.completions.create(**kwargs)

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
