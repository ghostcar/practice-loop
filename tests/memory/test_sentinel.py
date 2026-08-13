"""Tests for memoryctl sentinel (M4 preflight freshness)."""

from __future__ import annotations

import hashlib
import json
import subprocess

from tools.memoryctl import bootstrap as b
from tools.memoryctl import sentinel as s


def _git(root, *args):
    subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=True)


def _init_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _write_sentinel(root, **overrides):
    pack = {"kind": "context_pack", "payload": "x"}
    pack_bytes = json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    (root / s.PACK_RELPATH).parent.mkdir(parents=True, exist_ok=True)
    (root / s.PACK_RELPATH).write_text(pack_bytes, encoding="utf-8")
    data = {
        "schema_version": s.SCHEMA_VERSION,
        "kind": "session_sentinel",
        "session_id": "benchmark-1",
        "task_hash": "sha256:" + "0" * 64,
        "start_head": s.git_head_exact(root),
        "pack_hash": "sha256:" + hashlib.sha256(pack_bytes.encode("utf-8")).hexdigest(),
        "created_at": "2026-08-13T00:00:00Z",
        "status": "ready",
    }
    data.update(overrides)
    (root / s.SENTINEL_RELPATH).write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def test_sentinel_missing(tmp_path):
    root = _init_repo(tmp_path)
    ok, msg = s.check_sentinel(root)
    assert not ok
    assert "no preflight sentinel" in msg


def test_sentinel_ok_via_bootstrap(tmp_path):
    root = _init_repo(tmp_path)
    b.run_bootstrap(root, "a task", session_id="s1")
    ok, msg = s.check_sentinel(root)
    assert ok, msg


def test_sentinel_bad_status(tmp_path):
    root = _init_repo(tmp_path)
    _write_sentinel(root, status="blocked")
    ok, msg = s.check_sentinel(root)
    assert not ok
    assert "blocked" in msg


def test_sentinel_pack_hash_mismatch(tmp_path):
    root = _init_repo(tmp_path)
    _write_sentinel(root)
    # tamper with the context pack
    pack = root / s.PACK_RELPATH
    pack.write_text(pack.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    ok, msg = s.check_sentinel(root)
    assert not ok
    assert "pack_hash mismatch" in msg


def test_sentinel_stale_head(tmp_path):
    root = _init_repo(tmp_path)
    _write_sentinel(root, start_head="f" * 40)  # unknown commit, not an ancestor
    ok, msg = s.check_sentinel(root)
    assert not ok
    assert "not an ancestor" in msg


def test_sentinel_ttl(tmp_path):
    root = _init_repo(tmp_path)
    _write_sentinel(root, created_at="2020-01-01T00:00:00Z")
    ok, msg = s.check_sentinel(root, ttl_hours=1)
    assert not ok
    assert "TTL" in msg
    # without TTL it passes
    ok2, _ = s.check_sentinel(root)
    assert ok2
