"""Unit tests for tools.memoryctl.inventory."""

from __future__ import annotations

from tools.memoryctl.inventory import collect_inventory, render_report
from tools.memoryctl.schemas import DENYLIST_GLOBS, SECRET_DENYLIST_GLOBS, is_tracked_secret


def test_tracked_secret_helper():
    assert is_tracked_secret(".env")
    assert is_tracked_secret(".env.prod")
    assert is_tracked_secret("uploads/photo.jpg")
    assert is_tracked_secret("backup.sql.dump")
    # P2-4: sanitized template + vendored assets are not secrets
    assert not is_tracked_secret(".env.example")
    assert not is_tracked_secret("app/static/fonts/InterVariable.woff2")
    assert not is_tracked_secret("app/api/tasks.py")
    assert not is_tracked_secret("docs/state/FACTS.json")
    assert len(DENYLIST_GLOBS) >= 12
    assert len(SECRET_DENYLIST_GLOBS) >= 8


def test_inventory_reports_startup_and_memory(tmp_path):
    (tmp_path / "memory").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (tmp_path / "memory" / "STATUS.md").write_text("# Status\n", encoding="utf-8")
    (tmp_path / "memory" / "DECISIONS.md").write_text(
        "| ADR-001 | 2026-08-06 | X | Y | принято |\n| ADR-002 | 2026-08-06 | Z | W | принято |\n",
        encoding="utf-8",
    )
    (tmp_path / "memory" / "OPEN_QUESTIONS.md").write_text("## Q12 — Deferred\n", encoding="utf-8")
    inv = collect_inventory(tmp_path)
    assert inv["startup_context_bytes"] > 0
    assert any(f["path"] == "memory/STATUS.md" for f in inv["memory_files"])
    assert "ADR-001" in inv["adr_ids"]
    assert "ADR-002" in inv["adr_ids"]
    assert "Q12" in inv["open_questions"]
    assert inv["repository"] == tmp_path.name


def test_inventory_dangling_refs(tmp_path):
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "a.md").write_text("See [missing](docs/missing.md) and [ok](docs/ok.md).\n", encoding="utf-8")
    (tmp_path / "docs" / "ok.md").write_text("fine\n", encoding="utf-8")
    inv = collect_inventory(tmp_path)
    dangling = [t for _, t in inv["dangling_refs"]]
    assert "docs/missing.md" in dangling
    assert "docs/ok.md" not in dangling


def test_render_report_contains_sections(tmp_path):
    (tmp_path / "memory").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    inv = collect_inventory(tmp_path)
    report = render_report(inv)
    assert "Startup context" in report
    assert "memory/" in report
    assert "ADR" in report
    assert "Dangling refs" in report
    assert "Denied-but-tracked" in report
