"""Unit tests for tools.memoryctl.bootstrap (M3 base)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.memoryctl import bootstrap as b

VALID_CONTRACT = """---
schema_version: memory/v2alpha1
id: C-TEST
kind: contract
title: Test contract
status: active
authority: technical
owners:
  - project-owner
scope:
  - platform
source_refs:
  - path: AGENTS.md
    relation: origin
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 0000000000000000000000000000000000000000
review_on: source-change
---
# Test contract
"""

VALID_ADR = """---
schema_version: memory/v2alpha1
id: ADR-068
kind: adr
title: Memory v2
status: accepted
authority: technical
decision_type: technical
deciders:
  - project-owner
owners:
  - project-owner
scope:
  - engineering/memory
accepted_at: 2026-08-13T00:00:00Z
supersedes: []
superseded_by: null
source_refs:
  - path: memory/DECISIONS.md
    relation: origin
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 0000000000000000000000000000000000000000
review_on: source-change
---
# ADR-068
Memory v2 layered memory.
"""

VALID_WIKI = """---
schema_version: memory/v2alpha1
id: K-LOCKTIMER-SAFETY-STOP
kind: knowledge
title: Safety stop
status: active
authority: derived
owners:
  - project-owner
scope:
  - locktimer/core
source_refs:
  - path: PRODUCT_DECISIONS.md
    relation: defines
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 0000000000000000000000000000000000000000
review_on: source-change
---
# Safety stop
safety stop always available.
"""


def _git_init(root: Path) -> str:
    subprocess.run(["git", "init", "-q"], cwd=str(root), capture_output=True, timeout=30)
    subprocess.run(
        ["git", "-c", "user.email=t@e.com", "-c", "user.name=T", "add", "-A"],
        cwd=str(root),
        capture_output=True,
        timeout=30,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@e.com", "-c", "user.name=T", "commit", "-qm", "init"],
        cwd=str(root),
        capture_output=True,
        timeout=30,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True, timeout=30
    ).stdout.strip()


class TestClassify:
    def test_code_locktimer(self):
        c = b.classify_task("Переименовать list_sessions_by_date_range в locktimer service")
        assert "code" in c["classes"]
        assert "locktimer/core" in c["scopes"]

    def test_security_media(self):
        c = b.classify_task("Закрыть утечку секретов через публичный /uploads")
        assert "security" in c["classes"]
        assert "platform/media" in c["scopes"]

    def test_data_migration(self):
        c = b.classify_task("Сколько миграций и какой alembic head")
        assert "data/migrations" in c["scopes"]

    def test_defaults_when_unknown(self):
        c = b.classify_task("xyzzу nonsense")
        assert c["classes"] == ["code"]
        assert c["scopes"] == ["platform"]


class TestCollectDocs:
    def _setup(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
        (tmp_path / "knowledge.md").write_text(VALID_CONTRACT, encoding="utf-8")
        (tmp_path / "docs" / "adr").mkdir(parents=True)
        (tmp_path / "docs" / "wiki").mkdir(parents=True)
        (tmp_path / "docs" / "adr" / "ADR-068.md").write_text(VALID_ADR, encoding="utf-8")
        (tmp_path / "docs" / "wiki" / "K-LOCKTIMER-SAFETY-STOP.md").write_text(VALID_WIKI, encoding="utf-8")

    def test_l0_always_included(self, tmp_path):
        self._setup(tmp_path)
        docs = b.collect_docs(tmp_path, {"classes": ["code"], "scopes": ["social"]}, "что-то про social")
        paths = {d["path"] for d in docs}
        assert "AGENTS.md" in paths
        assert "knowledge.md" in paths

    def test_l1_scope_match(self, tmp_path):
        self._setup(tmp_path)
        docs = b.collect_docs(tmp_path, {"classes": ["code"], "scopes": ["locktimer/core"]}, "safety stop")
        paths = {d["path"] for d in docs}
        assert "docs/wiki/K-LOCKTIMER-SAFETY-STOP.md" in paths

    def test_l1_scope_mismatch_excluded(self, tmp_path):
        self._setup(tmp_path)
        docs = b.collect_docs(tmp_path, {"classes": ["code"], "scopes": ["social"]}, "social relationships")
        paths = {d["path"] for d in docs}
        assert "docs/wiki/K-LOCKTIMER-SAFETY-STOP.md" not in paths


class TestSearchCode:
    def test_finds_symbol(self, tmp_path):
        (tmp_path / "app").mkdir(parents=True)
        (tmp_path / "app" / "services.py").write_text(
            "def list_sessions_by_date_range():\n    pass\n", encoding="utf-8"
        )
        res = b.search_code(tmp_path, "переименовать list_sessions_by_date_range")
        assert any(r["path"] == "app/services.py" for r in res)
        assert "list_sessions_by_date_range" in res[0]["matched_by"]

    def test_skips_denylisted(self, tmp_path):
        (tmp_path / "app" / "static").mkdir(parents=True)
        (tmp_path / "app" / "static" / "htmx.min.js").write_text("var target_symbol=1;", encoding="utf-8")
        res = b.search_code(tmp_path, "target_symbol")
        assert all("htmx.min.js" not in r["path"] for r in res)


class TestImpactFrontier:
    def test_tests_migrations_call_sites(self, tmp_path):
        (tmp_path / "app").mkdir(parents=True)
        (tmp_path / "tests").mkdir(parents=True)
        (tmp_path / "alembic" / "versions").mkdir(parents=True)
        (tmp_path / "app" / "services.py").write_text(
            "def list_sessions_by_date_range():\n    pass\n", encoding="utf-8"
        )
        (tmp_path / "tests" / "test_services.py").write_text("list_sessions_by_date_range", encoding="utf-8")
        (tmp_path / "alembic" / "versions" / "025_x.py").write_text("list_sessions_by_date_range", encoding="utf-8")
        (tmp_path / "app" / "api.py").write_text(
            "from .services import list_sessions_by_date_range\n", encoding="utf-8"
        )
        code = [{"path": "app/services.py", "score": 3, "matched_by": ["list_sessions_by_date_range"]}]
        imp = b.build_impact_frontier(tmp_path, code, "list_sessions_by_date_range")
        assert "tests/test_services.py" in imp["tests"]
        assert "alembic/versions/025_x.py" in imp["migrations"]
        assert "app/api.py" in imp["call_sites"]


class TestBootstrap:
    def test_deterministic_and_ready(self, tmp_path):
        (tmp_path / "app").mkdir(parents=True)
        (tmp_path / "app" / "services.py").write_text(
            "def list_sessions_by_date_range():\n    pass\n", encoding="utf-8"
        )
        _git_init(tmp_path)
        p1 = b.bootstrap(tmp_path, "list_sessions_by_date_range", session_id="s1", now="2026-08-13T00:00:00Z")
        p2 = b.bootstrap(tmp_path, "list_sessions_by_date_range", session_id="s1", now="2026-08-13T00:00:00Z")
        assert p1 == p2
        assert p1["status"] == "ready"
        assert p1["start_head"] and len(p1["start_head"]) == 40
        assert p1["size_bytes"] > 0

    def test_writes_pack_and_sentinel(self, tmp_path):
        (tmp_path / "app").mkdir(parents=True)
        (tmp_path / "app" / "services.py").write_text("def foo_bar():\n    pass\n", encoding="utf-8")
        _git_init(tmp_path)
        pack, pack_path, sentinel_path = b.run_bootstrap(tmp_path, "foo_bar", session_id="s1", runtime_dir=".rt")
        assert pack_path.exists()
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
        assert sentinel["kind"] == "session_sentinel"
        assert sentinel["task_hash"] == pack["task_hash"]
        assert sentinel["start_head"] == pack["start_head"]
        assert sentinel["pack_hash"].startswith("sha256:")

    def test_empty_task_raises(self, tmp_path):
        try:
            b.bootstrap(tmp_path, "   ", session_id="s1")
        except ValueError:
            return
        raise AssertionError("expected ValueError for empty task")
