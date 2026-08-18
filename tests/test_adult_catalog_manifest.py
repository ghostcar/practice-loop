import json
from pathlib import Path

from tools.adult_catalog_manifest import lint_manifest, load_manifest, preview

MANIFEST_PATH = Path("data/seed/adult_activity_foundation.v1.json")


def test_foundation_manifest_is_valid() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    assert lint_manifest(manifest) == []
    assert manifest["import_allowed"] is False
    assert len(manifest["cards"]) == 7


def test_lint_rejects_required_media_and_penalty() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    card = manifest["cards"][0]
    card["evidence_policy"]["media_required"] = True
    card["gamification"]["penalty_enabled"] = True

    errors = lint_manifest(manifest)

    assert any("media_required" in error for error in errors)
    assert any("cannot enable penalties" in error for error in errors)


def test_preview_is_read_only_summary() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    result = preview(manifest)

    assert "import_allowed=False" in result
    assert "cards=7" in result
