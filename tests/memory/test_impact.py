"""Tests for memoryctl impact (M4 advisory coverage check)."""

from __future__ import annotations

import json
import subprocess

from tools.memoryctl import impact as im


def _git(root, *args):
    subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=True)


def _init_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "svc.py").write_text("def a():\n    pass\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("# note\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _write_pack(root, frontier):
    pack = {
        "schema_version": "memory/v2alpha1",
        "kind": "context_pack",
        "impact_frontier": frontier,
    }
    (root / im.PACK_RELPATH).parent.mkdir(parents=True, exist_ok=True)
    (root / im.PACK_RELPATH).write_text(
        json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_impact_no_pack(tmp_path):
    root = _init_repo(tmp_path)
    report = im.check_impact(root)
    assert report["has_pack"] is False


def test_impact_classifies_code_vs_docs(tmp_path):
    root = _init_repo(tmp_path)
    _write_pack(root, {"tests": [], "migrations": [], "call_sites": ["app/svc.py"]})

    # modify existing code file (covered) + modify a doc (always allowed)
    (root / "app" / "svc.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (root / "docs" / "note.md").write_text("# changed\n", encoding="utf-8")
    _git(root, "add", ".")

    report = im.check_impact(root)
    assert report["has_pack"] is True
    assert "app/svc.py" in report["in_scope"]
    assert "docs/note.md" in report["in_scope"]
    assert report["out_of_scope"] == []


def test_impact_flags_out_of_scope(tmp_path):
    root = _init_repo(tmp_path)
    _write_pack(root, {"tests": [], "migrations": [], "call_sites": []})

    # modify a code file NOT in the frontier
    (root / "app" / "svc.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    _git(root, "add", ".")

    report = im.check_impact(root)
    assert "app/svc.py" in report["out_of_scope"]
    assert report["notes"]


def test_impact_new_file_is_not_out_of_scope(tmp_path):
    root = _init_repo(tmp_path)
    _write_pack(root, {"tests": [], "migrations": [], "call_sites": []})

    (root / "app" / "new_feature.py").write_text("def new():\n    pass\n", encoding="utf-8")
    # untracked (not staged) — should be reported as a new file, not out-of-scope
    report = im.check_impact(root)
    assert "app/new_feature.py" in report["new_files"]
    assert report["out_of_scope"] == []


def test_path_classifiers():
    assert im._is_always_allowed("memory/SESSIONS.md")
    assert im._is_always_allowed("docs/adr/ADR-069.md")
    assert im._is_always_allowed("README.md")
    assert not im._is_always_allowed("app/svc.py")
    assert im._is_code("app/svc.py")
    assert im._is_code("tests/test_x.py")
    assert im._is_code("tools/memoryctl/impact.py")
    assert not im._is_code("README.md")
