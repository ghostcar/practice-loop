"""Localization (i18n/l10n) consistency tests.

Guards against the class of bugs that broke the frontend before (Session 41):

* JS reading `T.<flat>` while `page-i18n` nests translations under ``t``;
* JS reading short keys (``I18N.active``) while the dictionaries only have
  ``diets_active``;
* templates referencing ``t.<key>`` keys that do not exist in either locale
  (renders empty or silently falls back to an English default for RU users).

The rules enforced here are cheap static checks — they scan templates and
page JS and cross-reference the translation dictionaries.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.i18n import FALLBACK_LOCALE, SUPPORTED_LOCALES, get_translations
from app.i18n.en import EN
from app.i18n.helpers import detect_locale
from app.i18n.ru import RU

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"
JS_PAGES = ROOT / "app" / "static" / "js" / "pages"

LOCALES = ["en", "ru"]
DICTS = {"en": EN, "ru": RU}

# ---------------------------------------------------------------------------
# 1. Dictionaries: parity, empties, placeholders
# ---------------------------------------------------------------------------


def test_en_ru_key_parity():
    """Both locales expose exactly the same keys — no orphans, no gaps."""
    assert set(EN) == set(RU)


def test_no_empty_values():
    """No translation value is empty or whitespace-only."""
    for locale in LOCALES:
        empty = [k for k, v in DICTS[locale].items() if not str(v).strip()]
        assert not empty, f"{locale}: empty values for {empty}"


def test_placeholder_consistency():
    """``{var}`` placeholders used by EN must match RU for the same key."""
    ph = re.compile(r"\{[a-z_][a-z0-9_]*\}")
    for key in EN:
        en_vars = set(ph.findall(str(EN[key])))
        ru_vars = set(ph.findall(str(RU[key])))
        assert en_vars == ru_vars, f"{key}: placeholder mismatch EN={sorted(en_vars)} RU={sorted(ru_vars)}"


def test_get_translations_fallback():
    """Unknown locale falls back to EN; supported locales resolve."""
    assert get_translations("en") is EN
    assert get_translations("ru") is RU
    assert get_translations("xx") is EN
    assert FALLBACK_LOCALE in SUPPORTED_LOCALES


# ---------------------------------------------------------------------------
# 2. Template key references
# ---------------------------------------------------------------------------

# `t` is also used as a loop/object variable in a few templates (e.g.
# agent_chat.html iterates `msg.tools` as `t`). Those names are not
# translation keys.
NON_TRANSLATION_T_VARS = {
    "id",
    "result",
    "desc",
    "description",
    "is_done",
    "metric_type",
    "title",
    "name",
    "status",
    "type",
    "value",
    "slug",
    "kind",
    "category",
    "item",
    "date",
    "count",
    "total",
    "tool",
    "summary",
}

STATIC_KEY_PATTERNS = (
    re.compile(r"\{\{\s*t\.([a-z0-9_]+)\s*\}\}"),
    re.compile(r"t\.get\(\s*['\"]([a-z0-9_]+)['\"]"),
    re.compile(r"t\[\s*['\"]([a-z0-9_]+)['\"]\s*\]"),
)

# Dynamic lookups like t['health_phase_' + x] build the key at runtime.
DYNAMIC_PREFIX = re.compile(r"t\[\s*['\"]([a-z0-9_]+)_['\"]\s*\+")


def _template_static_keys() -> set[str]:
    keys: set[str] = set()
    for f in TEMPLATES.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        for pat in STATIC_KEY_PATTERNS:
            keys |= {m for m in pat.findall(txt) if m not in NON_TRANSLATION_T_VARS and not m.endswith("_")}
    return keys


def test_template_keys_exist_in_both_locales():
    """Every static ``t.<key>`` reference in templates exists in EN and RU."""
    keys = _template_static_keys()
    assert keys, "expected to find template keys"
    for locale in LOCALES:
        missing = sorted(k for k in keys if k not in DICTS[locale])
        assert not missing, f"{locale}: template keys missing from dictionary: {missing}"


def test_template_dynamic_prefixes_covered():
    """Dynamic ``t['prefix_' + x]`` lookups have at least one key per prefix."""
    prefixes: set[str] = set()
    for f in TEMPLATES.rglob("*.html"):
        prefixes |= set(DYNAMIC_PREFIX.findall(f.read_text(encoding="utf-8")))
    for prefix in prefixes:
        for locale in LOCALES:
            assert any(
                k.startswith(f"{prefix}_") for k in DICTS[locale]
            ), f"{locale}: no keys for dynamic prefix {prefix}_"


# ---------------------------------------------------------------------------
# 3. page-i18n / config JSON blocks
# ---------------------------------------------------------------------------


def test_page_i18n_blocks_are_valid_and_covered():
    """Each page-i18n block must parse; its t.* interpolations must exist."""
    for f in TEMPLATES.rglob("*.html"):
        txt = f.read_text(encoding="utf-8")
        for m in re.finditer(r'id="page-i18n">(.*?)</script>', txt, re.S):
            body = m.group(1)
            # hand-built blocks interpolate {{ t.key }}; verify those keys
            tkeys = set(re.findall(r"t\.([a-z0-9_]+)", body))
            tkeys -= NON_TRANSLATION_T_VARS
            missing = sorted(k for k in tkeys if k not in EN)
            assert not missing, f"{f.name}: page-i18n keys missing: {missing}"
            # blocks that are pure JSON ({{ {...} | tojson }}) must parse
            stripped = body.strip()
            if stripped.startswith("{{"):
                continue
            try:
                json.loads(body)
            except json.JSONDecodeError as exc:
                raise AssertionError(f"{f.name}: page-i18n is not valid JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# 4. JS i18n key references
# ---------------------------------------------------------------------------

JS_KEY_PATTERNS = (
    # flattened T.<key> (dashboard/calendar/import/inventory/tasks)
    re.compile(r"\bT\.([a-z][a-z0-9_]{2,})"),
    # diets.js reads the full dict via P.i18n
    re.compile(r"\bI18N\.([a-z][a-z0-9_]{2,})"),
    # protocol_builder.js reads i18n.* from the template config block
    re.compile(r"\bi18n\.([a-z][a-z0-9_]{2,})"),
)

# Keys on the flattened page-data object that are not translations.
PAGE_DATA_KEYS = {"t", "tg_bot_username", "has_llm", "diets"}

# calendar.js builds a *local* I18N alias object from T.* keys — its members
# are not dictionary keys, the underlying T.* lookups are what we validate.
# protocol_builder.js reads i18n.* aliases defined in the template's
# protocol-builder-config block (protocols_* / dp_* keys, covered by the
# template tests above).
LOCAL_ALIAS_KEYS = {
    "calendar_no_templates",
    "calendar_no_overrides",
    "calendar_default_marker",
    "calendar_window_count",
    "calendar_check_available",
    "calendar_check_unavailable",
    "calendar_btn_delete",
    # protocol_builder.js config aliases
    "remove_step",
    "step_title",
    "step_title_ph",
    "step_type",
    "step_timing",
    "step_offset",
    "step_duration",
    "dp_months",
    "dp_days",
    "dp_hours",
    "dp_minutes",
    "dp_seconds",
    "dp_presets",
}


def test_js_i18n_keys_exist():
    """Every i18n key accessed from page JS exists in the dictionaries."""
    refs: set[str] = set()
    for f in JS_PAGES.glob("*.js"):
        txt = f.read_text(encoding="utf-8")
        for pat in JS_KEY_PATTERNS:
            refs |= {
                m
                for m in pat.findall(txt)
                if not m.endswith("_")  # dynamic prefix (T['calendar_' + x])
            }
    refs -= PAGE_DATA_KEYS | LOCAL_ALIAS_KEYS
    assert refs, "expected to find JS i18n references"
    missing = sorted(k for k in refs if k not in EN)
    assert not missing, f"JS i18n keys missing from dictionaries: {missing}"


# ---------------------------------------------------------------------------
# 5. Locale detection
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, accept_language: str = ""):
        self.headers = {"accept-language": accept_language}


@pytest.mark.parametrize(
    ("user_locale", "accept", "expected"),
    [
        ("ru", "", "ru"),
        ("en", "ru", "en"),  # user preference wins over Accept-Language
        ("xx", "ru", "ru"),  # unsupported preference ignored
        (None, "en-US,en;q=0.9", "en"),
        (None, "ru-RU,ru;q=0.9", "ru"),
        (None, "fr-FR,fr;q=0.9", FALLBACK_LOCALE),  # unsupported → EN fallback
        (None, "", FALLBACK_LOCALE),
    ],
)
def test_detect_locale(user_locale, accept, expected):
    req = _FakeRequest(accept)
    assert detect_locale(req, user_locale) == expected
