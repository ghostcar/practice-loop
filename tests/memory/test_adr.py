"""Unit tests for tools.memoryctl.adr (M2 ADR split)."""

from __future__ import annotations

from tools.memoryctl.adr import check_bidirectional, compile_adrs, parse_legacy

LEGACY = """# Реестр решений (ADR)

| ID | Дата | Тема | Решение | Статус |
| --- | --- | --- | --- | --- |
| ADR-001 | 2026-08-06 | Semantic Masking | Отклонено: гибридная генерация | принято |
| ADR-002 | 2026-08-06 | Провайдеры LLM | BYOK | принято |
| ADR-003 | 2026-08-06 | Рейт-лимиты | Отложено | отложено |

### ADR-002 — Провайдеры LLM
**Decision:** BYOK: Omniroute, Groq, OpenRouter.

**Status:** Implemented.
"""


def test_parse_legacy_table_and_section():
    adrs = parse_legacy(LEGACY)
    assert set(adrs) == {1, 2, 3}
    assert adrs[1].topic == "Semantic Masking"
    assert adrs[1].status == "принято"
    assert adrs[3].status == "отложено"
    # detailed section body attached
    assert adrs[2].body is not None and "BYOK" in adrs[2].body
    assert adrs[1].body is None  # table-only


def test_compile_adrs_generates_files(tmp_path):
    decisions = tmp_path / "memory"
    decisions.mkdir()
    (decisions / "DECISIONS.md").write_text(LEGACY, encoding="utf-8")
    head = "a" * 40
    nums = compile_adrs(tmp_path, head=head)
    assert nums == [1, 2, 3]

    for n in nums:
        p = tmp_path / "docs" / "adr" / f"ADR-{n:03d}.md"
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert f"id: ADR-{n:03d}" in text
        assert f"last_verified_commit: {head}" in text
        assert "source_refs:" in text
        assert "memory/DECISIONS.md" in text

    # accepted ADR has accepted_at, deferred maps to proposed
    assert "status: accepted" in (tmp_path / "docs" / "adr" / "ADR-001.md").read_text(encoding="utf-8")
    assert "accepted_at: 2026-08-06T00:00:00Z" in (tmp_path / "docs" / "adr" / "ADR-001.md").read_text(encoding="utf-8")
    assert "status: proposed" in (tmp_path / "docs" / "adr" / "ADR-003.md").read_text(encoding="utf-8")
    assert (tmp_path / "docs" / "adr" / "README.md").exists()


def test_check_bidirectional_ok(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "DECISIONS.md").write_text(LEGACY, encoding="utf-8")
    compile_adrs(tmp_path, head="a" * 40)
    ok, msgs = check_bidirectional(tmp_path)
    assert ok, msgs
    assert any("bidirectionally" in m for m in msgs)


def test_check_bidirectional_missing(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "DECISIONS.md").write_text(LEGACY, encoding="utf-8")
    compile_adrs(tmp_path, head="a" * 40)
    (tmp_path / "docs" / "adr" / "ADR-003.md").unlink()
    ok, msgs = check_bidirectional(tmp_path)
    assert not ok
    assert any("ADR-003" in m for m in msgs)


def test_check_bidirectional_extra(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "DECISIONS.md").write_text(LEGACY, encoding="utf-8")
    compile_adrs(tmp_path, head="a" * 40)
    (tmp_path / "docs" / "adr" / "ADR-099.md").write_text("# stray\n", encoding="utf-8")
    ok, msgs = check_bidirectional(tmp_path)
    assert not ok
    assert any("ADR-099" in m for m in msgs)
