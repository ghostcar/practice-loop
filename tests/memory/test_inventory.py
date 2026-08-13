"""Unit tests for tools.memoryctl.inventory."""

from __future__ import annotations

from tools.memoryctl.inventory import _is_denied, collect_inventory, render_report
from tools.memoryctl.schemas import DENYLIST_GLOBS


def test_denylist_helper():
    assert _is_denied(".env")
    assert _is_denied(".env.prod")
    assert _is_denied(".agent-runtime/session.json")
    assert _is_denied(".memory-local/episodes/x.md")
    assert _is_denied("uploads/photo.jpg")
    assert _is_denied("app/static/fonts/InterVariable.woff2")
    assert _is_denied("examples/memory/MEMORY_SCHEMA.md")
    assert not _is_denied("app/api/tasks.py")
    assert not _is_denied("docs/state/FACTS.json")
    assert not _is_denied("memory/STATUS.md")
    assert len(DENYLIST_GLOBS) >= 12


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
