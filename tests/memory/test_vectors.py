"""Tests for memoryctl vectors — fusion, confirmation, degradation (no heavy deps)."""

from __future__ import annotations

import subprocess

from tools.memoryctl import vectors as v


def _git(root, *args):
    subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=True)


def _init_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "svc.py").write_text(
        '"""service module."""\n\ndef open_slot(x):\n    """Open a slot."""\n    return x\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_svc.py").write_text("def test_open_slot():\\n    pass\\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_rrf_fusion_merges_and_ranks():
    r1 = ["a", "b", "c"]
    r2 = ["b", "a", "d"]
    fused = v.reciprocal_rank_fusion(r1, r2)
    paths = [p for p, _ in fused]
    assert paths[0] == "a"  # rank 1 in r1 (1/61) + rank 2 in r2 (1/62) > b
    assert set(paths) == {"a", "b", "c", "d"}


def test_rrf_dedupes_within_ranking():
    fused = v.reciprocal_rank_fusion(["a", "a", "b"])
    assert [p for p, _ in fused] == ["a", "b"]


def test_point_id_is_deterministic_uuid():
    import hashlib

    ch = "sha256:" + hashlib.sha256(b"abc").hexdigest()
    assert v.point_id(ch) == v.point_id(ch)
    assert len(v.point_id(ch).replace("-", "")) == 32


def test_profile_hash_deterministic():
    assert v.profile_hash() == v.profile_hash()
    assert v.profile_hash().startswith("sha256:")


def test_embed_text_includes_scope_symbol():
    u = v.code_units._unit("app/locktimer/svc.py", "open_slot", 1, 2, "route", "python", "POST /open", "body")
    txt = v.embed_text(u)
    assert "locktimer/core" in txt
    assert "open_slot" in txt
    assert "POST /open" in txt


def test_is_available_graceful():
    # In the test environment the optional deps are (usually) absent; the contract
    # is that is_available never raises and returns (bool, str).
    ok, msg = v.is_available()
    assert isinstance(ok, bool)
    assert isinstance(msg, str)


def test_index_code_check_without_deps(tmp_path):
    root = _init_repo(tmp_path)
    info = v.index_code(root, mode="check")
    # deps may be absent (blocked) or present-with-no-manifest (stale)
    assert info.get("status") in ("blocked", "stale")
    # and full indexing degrades gracefully when deps absent
    info2 = v.index_code(root, mode="full")
    assert info2.get("available") is False or info2.get("status") == "ready"
    assert "reason" in info2 or info2.get("status") == "ready"


def test_search_code_degrades_without_deps(tmp_path):
    root = _init_repo(tmp_path)
    result = v.search_code(root, "open slot")
    # Either deps absent (degraded) or index stale (fresh HEAD not yet indexed)
    assert not result.get("available") or result.get("stale") is True or result.get("results") == []


def test_cosine():
    assert v.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert v.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert v.cosine([], []) == 0.0


def test_terms_stopword_filter():
    ts = v.terms("как работает open_slot для таймера")
    assert "open_slot" in ts
    assert "как" not in ts
