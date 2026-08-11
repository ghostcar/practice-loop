"""Title generator (ADR-042).

Builds a readable task title from an activity + its planned parameters using
a template with fallback logic. Empty template parts are skipped. Labels are
localized via a dict (EN/RU) — pass the translations object or a mapping.

Examples:
    "{count} {unit} — {activity_title}, {tool}, zone: {target_area}, intensity {intensity}/5, position: {position}"
    → "10 strikes — Spanking, hand, zone: buttocks, intensity 3/5"

Fallback chain (when no usable template/params):
    title_override → manual title → "<Activity title>" → localized "Free task: <title>"
"""

from __future__ import annotations

import re
from typing import Any

# ── Localized labels (i18n EN/RU) ───────────────────────────────────────

_LABELS_EN: dict[str, str] = {
    "tool": "tool",
    "target_area": "zone",
    "count": "count",
    "unit": "unit",
    "duration": "duration",
    "intensity": "intensity",
    "position": "position",
    "role": "role",
    "modifiers": "modifiers",
    "clothing": "clothing",
    "restraint": "restraint",
    "timing": "timing",
    "notes": "notes",
    "free_task": "Free task",
    "manual_title": "manual title",
}

_LABELS_RU: dict[str, str] = {
    "tool": "инструмент",
    "target_area": "зона",
    "count": "количество",
    "unit": "ед.",
    "duration": "длительность",
    "intensity": "интенсивность",
    "position": "позиция",
    "role": "роль",
    "modifiers": "условия",
    "clothing": "одежда",
    "restraint": "фиксация",
    "timing": "время",
    "notes": "заметки",
    "free_task": "Свободная задача",
    "manual_title": "ручной заголовок",
}

_LABELS_BY_LOCALE: dict[str, dict[str, str]] = {
    "en": _LABELS_EN,
    "ru": _LABELS_RU,
}

# Legacy raw-key fallback (no locale): snake_case → spaced words
_DEFAULT_LABELS: dict[str, str] = {}


def _labels(locale: str | None) -> dict[str, str]:
    return _LABELS_BY_LOCALE.get((locale or "en").lower(), _LABELS_EN)


def _fmt_value(key: str, value: Any) -> str:
    """Format a single param value for the title."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes"
    if isinstance(value, (int, float)):
        # intensity N/5 convention
        if key == "intensity" and isinstance(value, (int, float)) and 1 <= value <= 5:
            return f"{value}/5"
        return str(value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _lookup_title(key: str, value: Any, schema_defs: list[dict] | None) -> str | None:
    """Resolve enum option display title from the schema (e.g. 'hand' → 'Hand')."""
    if schema_defs is None or not isinstance(value, str):
        return None
    for d in schema_defs:
        if d.get("key") != key:
            continue
        options = d.get("options") or []
        for opt in options:
            if isinstance(opt, dict):
                if opt.get("value") == value:
                    return opt.get("title") or opt.get("value")
            elif str(opt) == value:
                return str(opt)
    return None


def _clean_joined(parts: list[str]) -> str:
    """Join non-empty parts, stripping artifacts left by empty template slots."""
    text = ", ".join(p for p in parts if p and p.strip())
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"[,;:/-]{2,}", ",", text)
    return text.strip(" ,-—:;/")


def generate_title(
    activity_title: str,
    params: dict | None = None,
    *,
    schema: Any = None,
    title_override: str | None = None,
    manual_title: str | None = None,
    template: str | None = None,
    locale: str | None = "en",
    free_task_label: str | None = None,
) -> str:
    """Generate a readable task title (ADR-042).

    Priority: title_override → manual_title → template-rendered → param list
    → activity title → localized free-task placeholder. Empty template parts
    are skipped. Locale-aware labels (EN/RU).
    """
    labels = _labels(locale)

    # Hard overrides win
    if title_override and title_override.strip():
        return title_override.strip()
    if manual_title and manual_title.strip():
        return manual_title.strip()

    # Collect param labels/values
    schema_defs = None
    try:
        from app.params import normalize_schema

        schema_defs = normalize_schema(schema)
    except (ValueError, TypeError):
        schema_defs = None

    parts: list[str] = []
    params = params or {}
    for key, value in params.items():
        if value is None or value == "" or value == []:
            continue
        option_title = _lookup_title(key, value, schema_defs)
        label = labels.get(key, _DEFAULT_LABELS.get(key, key.replace("_", " ")))
        display = option_title if option_title is not None else _fmt_value(key, value)
        parts.append(f"{label}: {display}")

    if template and "{" in template:
        result = template
        for key, value in params.items():
            token = "{" + key + "}"
            if token in result:
                fmt = _fmt_value(key, value)
                result = result.replace(token, fmt if fmt else "")
        result = result.replace("{activity_title}", activity_title or "")
        result = _clean_joined(result.split(","))
        if result:
            return result

    if parts:
        return f"{activity_title or ''}: {_clean_joined(parts)}".strip(" :,")

    if activity_title:
        return activity_title

    label = free_task_label or labels.get("free_task", "Free task")
    return f"{label}: [{labels.get('manual_title', 'manual title')}]"
