from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "app" / "static" / "js" / "pages" / "body_parts.js"


def test_body_parts_frontend_uses_api_titles_not_missing_title_field() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "node.title_ru || node.title_en || node.slug" in source
    assert "escHtml(title)" in source
    assert "n.title_ru || n.title_en || n.slug" in source
    assert "aria-hidden=\\\"true\\\"" in source
    assert "escHtml(node.slug || '')" not in source
