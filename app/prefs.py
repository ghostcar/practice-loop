"""User preferences (Step 9e — DESIGN_V2 §16 customization/discretion).

Preferences live in a JSONB column on ``users.prefs``; this module provides the
typed view over that blob, defaults, validation and the request-scoped
ContextVar that the template context processor reads.

Schema (all keys optional — missing keys fall back to defaults)::

    {
        "accent": "ember" | "sage" | "slate",          # approved muted accent set
        "density": "comfortable" | "compact",          # default list density
        "dash_blocks": {                               # dashboard blocks
            "order": ["header", "stats", ...],         # render order (full list)
            "hidden": ["quick", ...],                  # blocks to hide
        },
        "discretion": {
            "mode": "off" | "always" | "schedule",     # §12
            "start": "22:00",                          # local time, schedule mode
            "end": "07:00",
        },
        "blur": 0 | 1 | 2,                             # sensitive-image blur level
        "theme_choice": "dark" | "light" | "system",   # resolved on client
    }
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.timeutils import local_now

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

ACCENTS = ("ember", "sage", "slate")
DENSITIES = ("comfortable", "compact")
THEME_CHOICES = ("dark", "light", "system")
DISCRETION_MODES = ("off", "always", "schedule")
BLUR_LEVELS = (0, 1, 2)
# LLM режимы (ADR-087): safe — нейтральный пересказ фактов (default);
# expanded — рекомендации/советы/интерпретация (влияет на все LLM-блоки).
LLM_MODES = ("safe", "expanded")

# Dashboard blocks in default order. Keys must match the `data-dash-block`
# markers in dashboard_v2.html.
DASH_BLOCKS = (
    "header", "stats", "charts", "summaries", "xp", "quick", "today", "medication", "health", "journal", "care", "timer"
)

DEFAULT_PREFS: dict[str, Any] = {
    "accent": "ember",
    "density": "comfortable",
    "dash_blocks": {"order": list(DASH_BLOCKS), "hidden": []},
    "discretion": {"mode": "off", "start": "22:00", "end": "07:00"},
    "blur": 0,
    "theme_choice": "dark",
    "llm_mode": "safe",
}

DISCRETION_LABELS = (
    "today", "tasks", "sessions", "catalog", "training", "diets",
    "inventory", "measurements", "schedule", "body_parts", "calendar",
    "points", "achievements", "media", "timer", "social",
)


@dataclass(frozen=True)
class UserPrefs:
    """Typed, validated view over the raw ``users.prefs`` JSON blob."""

    accent: str = "ember"
    density: str = "comfortable"
    dash_blocks: dict = field(default_factory=lambda: {"order": list(DASH_BLOCKS), "hidden": []})
    discretion: dict = field(default_factory=lambda: {"mode": "off", "start": "22:00", "end": "07:00"})
    blur: int = 0
    theme_choice: str = "dark"
    llm_mode: str = "safe"

    # --- convenience ------------------------------------------------------

    @property
    def dash_visible(self) -> list[str]:
        order = self.dash_blocks.get("order") or list(DASH_BLOCKS)
        hidden = set(self.dash_blocks.get("hidden") or [])
        return [b for b in order if b not in hidden]

    @property
    def discretion_mode(self) -> str:
        return self.discretion.get("mode", "off")

    def discretion_active_at(self, now: datetime | None = None) -> bool:
        """True when the discretion mode applies at the given moment (local tz)."""
        mode = self.discretion_mode
        if mode == "always":
            return True
        if mode == "schedule":
            t = (now or local_now()).time()
            start = self.discretion.get("start", "22:00")
            end = self.discretion.get("end", "07:00")
            return _in_window(t.strftime("%H:%M"), start, end)
        return False


def _in_window(t: str, start: str, end: str) -> bool:
    """True if time ``t`` (HH:MM) lies in [start, end), supporting overnight windows."""
    try:
        h, m = int(t[:2]), int(t[3:5])
        s_h, s_m = int(start[:2]), int(start[3:5])
        e_h, e_m = int(end[:2]), int(end[3:5])
    except (ValueError, IndexError):
        return False
    minutes = h * 60 + m
    start_min = s_h * 60 + s_m
    end_min = e_h * 60 + e_m
    if start_min <= end_min:
        return start_min <= minutes < end_min
    # overnight window, e.g. 22:00 → 07:00
    return minutes >= start_min or minutes < end_min


# ---------------------------------------------------------------------------
# (De)serialization
# ---------------------------------------------------------------------------


def raw_dict(value: Any) -> dict:
    """Coerce a stored prefs value (dict / JSON string / None) to a dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        import json

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def sanitize_prefs(raw: dict | None) -> dict:
    """Validate/normalize a raw JSON blob into a full prefs dict (with defaults)."""
    raw = dict(raw or {})
    out: dict[str, Any] = {}

    out["accent"] = raw.get("accent") if raw.get("accent") in ACCENTS else "ember"
    out["density"] = raw.get("density") if raw.get("density") in DENSITIES else "comfortable"
    out["theme_choice"] = raw.get("theme_choice") if raw.get("theme_choice") in THEME_CHOICES else "dark"
    out["blur"] = raw.get("blur") if raw.get("blur") in BLUR_LEVELS else 0
    out["llm_mode"] = raw.get("llm_mode") if raw.get("llm_mode") in LLM_MODES else "safe"

    blocks = raw.get("dash_blocks") or {}
    order = [b for b in (blocks.get("order") or list(DASH_BLOCKS)) if b in DASH_BLOCKS]
    # append blocks missing from the stored order (new blocks added later)
    for b in DASH_BLOCKS:
        if b not in order:
            order.append(b)
    hidden = [b for b in (blocks.get("hidden") or []) if b in DASH_BLOCKS]
    out["dash_blocks"] = {"order": order, "hidden": hidden}

    disc = raw.get("discretion") or {}
    mode = disc.get("mode") if disc.get("mode") in DISCRETION_MODES else "off"
    start = disc.get("start") if _valid_hhmm(disc.get("start")) else "22:00"
    end = disc.get("end") if _valid_hhmm(disc.get("end")) else "07:00"
    out["discretion"] = {"mode": mode, "start": start, "end": end}

    return out


def _valid_hhmm(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return False
    try:
        int(value[:2])
        int(value[3:])
        return True
    except ValueError:
        return False


def prefs_from_dict(raw: dict | None) -> UserPrefs:
    return UserPrefs(**sanitize_prefs(raw))


def neutral_notification(
    prefs: UserPrefs | None,
    title: str,
    body: str | None,
    locale: str = "en",
) -> tuple[str, str | None]:
    """Neutralize a notification title/body when discretion is active (DESIGN_V2 §12).

    Discretion changes notification texts to a neutral localized variant so lock
    screen / Telegram previews do not reveal the subject context. Data, rules,
    safety actions and audit are never touched — only the presentation text.
    """
    if prefs is None or not prefs.discretion_active_at():
        return title, body
    from app.i18n import get_translations

    t = get_translations(locale)
    return t.get("dscr_notif_title", title), t.get("dscr_notif_body", body)


# ---------------------------------------------------------------------------
# Request-scoped ContextVar (mirrors app.timeutils client_tz pattern)
# ---------------------------------------------------------------------------

_prefs_var: contextvars.ContextVar[UserPrefs | None] = contextvars.ContextVar(
    "user_prefs", default=None
)


def set_prefs(prefs: UserPrefs) -> contextvars.Token:
    return _prefs_var.set(prefs)


def reset_prefs(token: contextvars.Token) -> None:
    _prefs_var.reset(token)


def get_prefs() -> UserPrefs:
    return _prefs_var.get() or UserPrefs()
