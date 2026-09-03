from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "app" / "static" / "js" / "pages" / "body_parts.js"


def test_body_parts_frontend_uses_localized_names_without_rendering_slugs() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "return node.title_ru || node.title_en || '';" in source
    assert "escHtml(title)" in source
    assert "node.title_en" in source
    assert "node.slug" not in source


def test_body_parts_frontend_renders_readable_groups_not_collapsed_tree_controls() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "systemLabels" in source
    assert "data-body-system" in source
    assert "treeEl.dataset.sensitive" in source
    assert "_bpToggle" not in source
    assert "\\u25b8" not in source
