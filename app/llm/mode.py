"""LLM mode helper (ADR-087) — shared across all LLM blocks.

``prefs.llm_mode`` (safe | expanded) controls how freely the assistant
interprets the user's data:

- ``safe`` (default): factual, neutral, no unsolicited advice.
- ``expanded``: the assistant may give practical recommendations and advice.

The mode is a *prompt-frame* lever only — it never bypasses provider safety
filters and never masks content (AGENTS.md compliance red line). The
"not a doctor" disclaimer lives in the user interface, NOT in the prompts
(owner decision, Session 137).

This module centralizes the hint text so every LLM block uses the same wording.
"""

from __future__ import annotations

from app.prefs import LLM_MODES, get_prefs

# Appended to a system prompt when the user is in expanded mode.
EXPANDED_HINT = (
    "\n\nThe user has enabled expanded mode: you may give practical, personalized "
    "recommendations and advice to help them, in addition to the factual response. "
    "Keep suggestions grounded in the provided data and clearly separate "
    "interpretations from confirmed facts."
)

# Appended when the user is in safe mode (explicit, so behaviour is stable even
# if a future default changes).
SAFE_HINT = (
    "\n\nThe user is in safe mode: stay factual and neutral, separate facts from "
    "assumptions, and do not give unsolicited advice or recommendations."
)


def llm_mode_hint(llm_mode: str | None = None) -> str:
    """Return the prompt-frame hint for the given mode (default: from prefs)."""
    mode = llm_mode or get_prefs().llm_mode
    if mode == "expanded":
        return EXPANDED_HINT
    return SAFE_HINT


def resolve_llm_mode(llm_mode: str | None = None) -> str:
    """Normalize a mode value (explicit param wins, else prefs, else safe)."""
    if llm_mode in LLM_MODES:
        return llm_mode
    return get_prefs().llm_mode
