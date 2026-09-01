from __future__ import annotations

from pathlib import Path

TEMPLATE = Path(__file__).parents[1] / "app" / "templates" / "tasks.html"


def test_tasks_template_handles_missing_active_config_cost() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "active_config.total_cost or 0" in source
    assert "active_config.total_tokens or 0" in source
