"""Icon pack integration tests (design/icons/INTEGRATION_AGENT.md §7.8).

Verifies:
1. Every `{{ icon('name', ...) }}` / `{{ icon("name", ...) }}` usage in Jinja
   templates resolves to an `icon-{name}` symbol in app/static/icons/sprite.svg.
2. The sprite file exists and is the pack-generated sprite.
3. Static allowlist of JS plIcon() names is covered by the sprite.
"""

import re
from pathlib import Path

SPRITE = Path("app/static/icons/sprite.svg")
TEMPLATES_DIR = Path("app/templates")

# Static allowlist of icon names used from JS (window.plIcon) — kept in sync
# with app/static/js usage; server-side check that they exist in the sprite.
JS_ICON_NAMES = {"ai", "camera", "close", "more"}

MACRO_CALL_RE = re.compile(r"\{\{\s*icon\(\s*(['\"])([a-z0-9-]+)\1\s*[,)]")


def _sprite_ids() -> set[str]:
    assert SPRITE.exists(), f"sprite missing: {SPRITE}"
    text = SPRITE.read_text(encoding="utf-8")
    ids = re.findall(r'id="(icon-[^"]+)"', text)
    assert ids, "sprite has no icon-* symbols"
    return {i.removeprefix("icon-") for i in ids}


def test_sprite_exists_and_has_symbols() -> None:
    ids = _sprite_ids()
    assert len(ids) >= 100, f"expected 100+ symbols, got {len(ids)}"


def test_all_jinja_icon_names_exist_in_sprite() -> None:
    ids = _sprite_ids()
    used: set[str] = set()
    for path in TEMPLATES_DIR.rglob("*.html"):
        matches = MACRO_CALL_RE.findall(path.read_text(encoding="utf-8"))
        used.update(name for _, name in matches)
    assert used, "no icon() macro calls found — integration incomplete?"
    missing = sorted(used - ids)
    assert not missing, f"icon names used in templates but missing from sprite: {missing}"


def test_js_icon_names_exist_in_sprite() -> None:
    ids = _sprite_ids()
    missing = sorted(JS_ICON_NAMES - ids)
    assert not missing, f"JS plIcon names missing from sprite: {missing}"


def test_no_dangling_svg_in_templates() -> None:
    """After integration, no raw <svg> should remain in templates except the
    macro definition itself (unique illustration SVGs are allowed per §7.2,
    but we expect none right now)."""
    offenders = []
    for path in TEMPLATES_DIR.rglob("*.html"):
        if "components/icon.html" in str(path):
            continue
        if "<svg" in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    assert not offenders, f"raw <svg> remaining in templates: {offenders}"


# Emoji used as content VALUES (not icons) — stored in DB / select options
# where SVG icons cannot render. Kept intentionally; see PLAN.md debt list.
CONTENT_EMOJI_FILES = {"app/templates/social/verification.html"}

# Exact legacy debt.  New files cannot be added silently; removing an entry
# requires replacing each glyph with a semantic icon() call, not deleting UI.
LEGACY_EMOJI_TEMPLATE_FILES = {
    "app/templates/admin_ai_generator.html",
    "app/templates/admin_catalog_editor.html",
    "app/templates/admin_schema_builder.html",
    "app/templates/aftercare.html",
    "app/templates/agent_chat.html",
    "app/templates/care_builder.html",
    "app/templates/catalog_public.html",
    "app/templates/components/ambient_player.html",
    "app/templates/components/live_camera_observer.html",
    "app/templates/components/schema_builder.html",
    "app/templates/consent_matrix.html",
    "app/templates/dashboard_v2.html",
    "app/templates/discretion_bailout.html",
    "app/templates/ds_checkins.html",
    "app/templates/ds_keyholder.html",
    "app/templates/ds_my_top.html",
    "app/templates/ds_portal.html",
    "app/templates/entity_edit.html",
    "app/templates/health.html",
    "app/templates/health_body_cycle.html",
    "app/templates/insights.html",
    "app/templates/insights_medical_exporter.html",
    "app/templates/insights_report.html",
    "app/templates/inventory.html",
    "app/templates/inventory_maintenance.html",
    "app/templates/media_progress.html",
    "app/templates/medication.html",
    "app/templates/prompt_library_user.html",
    "app/templates/quests.html",
    "app/templates/sessions.html",
    "app/templates/sessions_ambient.html",
    "app/templates/sessions_coop.html",
    "app/templates/sessions_live.html",
    "app/templates/sessions_rules_builder.html",
    "app/templates/sessions_wizard.html",
    "app/templates/social/leaderboard.html",
    "app/templates/social/pillory.html",
    "app/templates/training.html",
    "app/templates/training_adaptive.html",
    "app/templates/training_builder.html",
}

LEGACY_EMOJI_JS_FILES = {"app/static/js/pages/inventory.js"}

# Emoji symbols that are only ever allowed as content values, never as UI icons.
EMOJI_RE = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f0ff]")


def test_no_emoji_icons_in_templates() -> None:
    """After the Step 8 sweep, templates must not use emoji as UI icons.

    Exceptions: files where emoji are content values (reaction buttons stored
    in DB, select-option markers) — see CONTENT_EMOJI_FILES. New emoji icons
    anywhere else are a regression against the icon-pack obligation.
    """
    offenders = []
    for path in TEMPLATES_DIR.rglob("*.html"):
        rel = str(path)
        if rel in CONTENT_EMOJI_FILES or rel in LEGACY_EMOJI_TEMPLATE_FILES:
            continue
        if EMOJI_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert not offenders, f"new emoji icon files outside the legacy allowlist: {offenders}"
    actual_legacy = {
        str(path)
        for path in TEMPLATES_DIR.rglob("*.html")
        if str(path) in LEGACY_EMOJI_TEMPLATE_FILES and EMOJI_RE.search(path.read_text(encoding="utf-8"))
    }
    assert actual_legacy == LEGACY_EMOJI_TEMPLATE_FILES, "legacy emoji allowlist is stale; remove migrated files"


def test_no_emoji_icons_in_js() -> None:
    """JS-generated UI must use window.plIcon, not emoji glyphs."""
    offenders = []
    for path in (TEMPLATES_DIR.parent / "static" / "js").rglob("*.js"):
        if EMOJI_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path))
    assert (
        set(offenders) == LEGACY_EMOJI_JS_FILES
    ), f"emoji JS allowlist drift: actual={offenders}, expected={sorted(LEGACY_EMOJI_JS_FILES)}"
