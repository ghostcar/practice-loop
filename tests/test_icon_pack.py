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
