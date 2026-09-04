"""Unit tests for tools.memoryctl.adr (M2 ADR split)."""

from __future__ import annotations

from tools.memoryctl.adr import (
    _normalize_section_status,
    _status,
    check_bidirectional,
    compile_adrs,
    parse_legacy,
)

MARKER = "Compiled by `memoryctl adr compile`"

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


# --- mixed-format registry regression tests (2026-09-03 reconciliation) ---


def test_english_status_and_legacy6_row_layout():
    text = """| ID | Тема | Категория | Дата | Коммит | Статус |
| --- | --- | --- | --- | --- | --- |
| ADR-172 | diets extraction | refactor | 2026-08-25 | 07421c75 | accepted |
"""
    adrs = parse_legacy(text)
    assert 172 in adrs
    assert adrs[172].date == "2026-08-25"
    assert adrs[172].topic == "diets extraction"
    assert "accepted" in adrs[172].status
    assert _status(172, adrs[172].status) == "accepted"


def test_colon_and_h2_section_headers_are_parsed():
    text = """| ADR-161 | 2026-08-24 | care split | thin routes | принято |

## ADR-161: care.py → care_service.py
Body of colon-style section.

### ADR-153: Notification channels
Body of H3 colon-style section.
"""
    adrs = parse_legacy(text)
    assert adrs[161].body is not None and "colon-style" in adrs[161].body
    # section-only ADR (no row) is promoted into the registry
    assert 153 in adrs
    assert "H3 colon-style" in (adrs[153].body or "")


def test_html_comments_are_skipped():
    text = """| ADR-001 | 2026-08-06 | t | d | принято |
<!--
| ADR-998 | 2026-01-01 | retired row | x | отклонено |
-->
<!-- ADR-999: номер не использован. -->
"""
    adrs = parse_legacy(text)
    assert set(adrs) == {1}


def test_section_only_adr_promoted_with_date_and_status():
    text = """| ADR-001 | 2026-08-06 | t | d | принято |

### ADR-124 — Prompt library
**Date:** 2026-08-20
**Decision:** two-level library.
**Status:** ✅ Реализовано, 8 новых тестов.
"""
    adrs = parse_legacy(text)
    assert 124 in adrs
    assert adrs[124].date == "2026-08-20"
    assert adrs[124].status == "принято"


def test_decision_with_literal_pipes_roundtrips():
    text = (
        "| ADR-048 | 2026-08-11 | Варианты приложения | "
        "`APP_PRODUCT_VARIANT=tracker|timer|combined` управляет registry | принято |\n"
    )
    adrs = parse_legacy(text)
    assert adrs[48].decision == "`APP_PRODUCT_VARIANT=tracker|timer|combined` управляет registry"


def test_compile_never_overwrites_hand_written_files(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "DECISIONS.md").write_text(LEGACY, encoding="utf-8")
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    handwritten = "# ADR-001 — hand-written\n\ncustom reviewed content\n"
    (adr_dir / "ADR-001.md").write_text(handwritten, encoding="utf-8")
    compile_adrs(tmp_path, head="a" * 40)
    assert (adr_dir / "ADR-001.md").read_text(encoding="utf-8") == handwritten


def test_compile_adds_body_commit_provenance_and_normalizes_metadata(tmp_path):
    (tmp_path / "memory").mkdir()
    legacy = """| ADR-120 | 2026-08-19 | Quests | Added quests | принято |

### ADR-120 — Quests
**Date:** 2026-08-19
**Decision:** Implemented in commit `53a0979487e7a3f7881259aceea94ecb2add843e`.
"""
    (tmp_path / "memory" / "DECISIONS.md").write_text(legacy, encoding="utf-8")
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-120.md").write_text(
        """---
 schema_version: memory/v2alpha1
 id: ADR-120
 kind: adr
 title: old
 status: accepted
 accepted_at: 2026-08-19T00:00:00Z
 last_verified_at: 2026-08-13T00:00:00Z
 last_verified_commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
---

# old

> Compiled by `memoryctl adr compile`
""".replace("\n ", "\n"),
        encoding="utf-8",
    )
    compile_adrs(tmp_path, head="b" * 40)
    generated = (adr_dir / "ADR-120.md").read_text(encoding="utf-8")
    assert "last_verified_at: 2026-08-19T00:00:00Z" in generated
    assert "last_verified_commit: 53a0979487e7a3f7881259aceea94ecb2add843e" in generated
    assert "sha: 53a0979487e7a3f7881259aceea94ecb2add843e" in generated
    assert generated.endswith("relying on it.\n")
    assert not generated.endswith("\n\n")


def test_compile_preserves_provenance_and_is_churn_free(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "DECISIONS.md").write_text(LEGACY, encoding="utf-8")
    compile_adrs(tmp_path, head="a" * 40)
    adr1 = tmp_path / "docs" / "adr" / "ADR-001.md"
    before = adr1.read_text(encoding="utf-8")
    # recompile with a different HEAD and later verified_at: no content change
    compile_adrs(tmp_path, head="b" * 40)
    after = adr1.read_text(encoding="utf-8")
    assert before == after
    assert "last_verified_commit: " + "a" * 40 in after


def test_normalize_section_status_reports():
    assert _normalize_section_status("✅ Реализовано, 8 тестов") == "принято"
    assert _normalize_section_status("Реализовано в Сессии 120") == "принято"
    assert _normalize_section_status("принято") == "принято"


def test_status_compound_first_token():
    assert _status(1, "принят, реализован") == "accepted"
    assert _status(1, "Accepted") == "accepted"
    assert _status(1, "принято.") == "accepted"


def test_section_body_stops_at_interleaved_registry_row():
    text = """| ADR-001 | 2026-08-06 | first | decision | принято |

### ADR-001 — Detailed decision
Body only.
| ADR-002 | 2026-08-07 | second | decision | принято |
"""
    adrs = parse_legacy(text)
    assert adrs[1].body == "Body only."
    assert 2 in adrs
