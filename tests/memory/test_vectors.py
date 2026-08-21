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
    # no manifest written yet
    assert info.get("status") == "stale"


def test_index_code_blocked_without_omniroute_config(tmp_path, monkeypatch):
    # Isolate from the host env: the real project .env may leak OMNIROUTE_*
    # into os.environ via dotenv loading in conftest/app imports.
    monkeypatch.delenv("OMNIROUTE_HOST", raising=False)
    monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
    root = _init_repo(tmp_path)
    info = v.index_code(root, mode="full")
    # tmp repo has no .env → either deps absent (available=False) or
    # Omniroute keys missing (available=True, status=blocked)
    assert info.get("available") is False or info.get("status") == "blocked"
    if info.get("available"):
        assert "OMNIROUTE" in info.get("reason", "")
    else:
        assert "reason" in info


def test_omniroute_settings_reads_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("OMNIROUTE_HOST", raising=False)
    monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OMNIROUTE_HOST=llm.example.ru\nOMNIROUTE_API_KEY=sk-test-123\n", encoding="utf-8")
    s = v.omniroute_settings(tmp_path)
    assert s["OMNIROUTE_HOST"] == "llm.example.ru"
    assert s["OMNIROUTE_API_KEY"] == "sk-test-123"


def test_omniroute_settings_env_overrides_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OMNIROUTE_HOST=from-file\n", encoding="utf-8")
    monkeypatch.setenv("OMNIROUTE_HOST", "from-env")
    s = v.omniroute_settings(tmp_path)
    assert s["OMNIROUTE_HOST"] == "from-env"


def test_search_code_degrades_without_deps(tmp_path):
    root = _init_repo(tmp_path)
    result = v.search_code(root, "open slot")
    # Either deps absent (degraded), config missing, or index stale
    assert (
        not result.get("available")
        or result.get("stale") is True
        or result.get("results") == []
        or "OMNIROUTE" in result.get("reason", "")
    )


def test_cosine():
    assert v.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert v.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert v.cosine([], []) == 0.0


def test_terms_stopword_filter():
    ts = v.terms("как работает open_slot для таймера")
    assert "open_slot" in ts
    assert "как" not in ts
