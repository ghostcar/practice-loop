"""LLM source policy by product section."""

from __future__ import annotations

import json

from app.config import settings

DEFAULT_LLM_SECTIONS = (
    "tasks",
    "training",
    "insights",
    "diet",
    "health",
    "care",
    "journal",
    "timer",
    "media",
    "assistant",
)


def personal_llm_sections() -> frozenset[str]:
    try:
        raw = json.loads(settings.personal_llm_sections_json or "[]")
    except (TypeError, ValueError):
        return frozenset()
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(item).strip() for item in raw if str(item).strip())


def is_personal_allowed(section: str) -> bool:
    """Return whether BYOK is allowed for a product section."""
    return section in personal_llm_sections()


def available_sections() -> tuple[str, ...]:
    """Stable section list used by the settings UI and documentation."""
    return DEFAULT_LLM_SECTIONS
