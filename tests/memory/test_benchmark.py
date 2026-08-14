"""Tests for memoryctl benchmark (M3 base retrieval scoring + report)."""

from __future__ import annotations

import json

from tools.memoryctl import benchmark as b


def _tmp_repo(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "services.py").write_text(
        "def list_sessions_by_date_range():\n    pass\n\ndef foo_bar():\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_services.py").write_text(
        "from app.services import list_sessions_by_date_range\n", encoding="utf-8"
    )
    return tmp_path


def test_pattern_matching():
    assert b._pattern_hit("app/services.py", {"app/services.py"})
    assert b._pattern_hit("alembic/versions/*025*", {"alembic/versions/18554078_025_x.py"})
    assert not b._pattern_hit("alembic/versions/*025*", {"alembic/versions/024_y.py"})
    assert b._matched(["app/services.py", "app/nope.py"], {"app/services.py"}) == ["app/services.py"]


def test_evaluate_task_finds_expected_code(tmp_path):
    root = _tmp_repo(tmp_path)
    task = {
        "id": 1,
        "query": "list_sessions_by_date_range",
        "expected_code": ["app/services.py", "tests/test_services.py"],
        "expected_docs": [],
        "forbidden": [],
    }
    res = b.evaluate_task(root, task, now="2026-08-13T00:00:00Z")
    assert res["recall_code"] == 1.0
    assert res["recall_at_5"] == 1.0
    assert res["mrr"] == 1.0
    assert res["missing"] == []
    assert res["pack_size_bytes"] > 0


def test_evaluate_task_forbidden_and_docs(tmp_path):
    root = _tmp_repo(tmp_path)
    task = {
        "id": 2,
        "query": "list_sessions_by_date_range",
        "expected_code": ["app/services.py"],
        "expected_docs": ["PRODUCT_DECISIONS.md"],
        "forbidden": ["tests/*"],
    }
    res = b.evaluate_task(root, task, now="2026-08-13T00:00:00Z")
    assert res["recall_code"] == 1.0
    # PRODUCT_DECISIONS.md is out of scope → docs recall 0 and listed missing
    assert res["recall_docs"] == 0.0
    assert "PRODUCT_DECISIONS.md" in res["missing"]
    # test file was retrieved but is forbidden
    assert res["forbidden_hits"] == ["tests/test_services.py"]


def test_run_benchmark_structure_and_determinism():
    root = b.Path(__file__).resolve().parents[2]
    r1 = b.run_benchmark(root, now="2026-08-13T00:00:00Z")
    r2 = b.run_benchmark(root, now="2026-08-13T00:00:00Z")

    assert r1["kind"] == "benchmark_report"
    assert r1["task_count"] == len(b.BENCHMARK_TASKS) == 12
    assert r1["thresholds"] == b.THRESHOLDS
    assert isinstance(r1["meets_admission_thresholds"], bool)
    agg = r1["aggregate"]
    for key in (
        "mean_recall_at_5",
        "mean_recall_code",
        "mean_recall_docs",
        "mean_recall_all",
        "mean_mrr",
        "median_pack_size_bytes",
        "max_pack_size_bytes",
        "total_extra_reads",
        "forbidden_hits",
        "tasks_full_code_recall",
        "mean_impact_recall",
        "tasks_with_impact",
    ):
        assert key in agg, key
    # at least 3 of the 12 tasks carry impact_symbols (metric must be exercised)
    assert agg["tasks_with_impact"] >= 3
    assert agg["mean_impact_recall"] is not None and 0.0 <= agg["mean_impact_recall"] <= 1.0
    # every task has the metric fields
    for t in r1["tasks"]:
        assert 0.0 <= t["recall_at_5"] <= 1.0
        assert 0.0 <= t["mrr"] <= 1.0
        assert t["pack_size_bytes"] > 0
    # deterministic given fixed now + same tree
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_impact_recall_ground_truth(tmp_path):
    root = _tmp_repo(tmp_path)
    ground = b.build_impact_ground_truth(root, ["list_sessions_by_date_range"])
    # definition site + the test consumer
    assert ground == {"app/services.py", "tests/test_services.py"}
    # symbol absent → empty set
    assert b.build_impact_ground_truth(root, ["never_used_symbol_xyz"]) == set()


def test_evaluate_task_reports_impact_recall(tmp_path):
    root = _tmp_repo(tmp_path)
    task = {
        "id": 1,
        "query": "list_sessions_by_date_range consumers",
        "expected_code": ["app/services.py"],
        "expected_docs": [],
        "forbidden": [],
        "impact_symbols": ["list_sessions_by_date_range"],
    }
    res = b.evaluate_task(root, task, now="2026-08-13T00:00:00Z")
    # ground truth = {app/services.py, tests/test_services.py}; the lexical
    # search retrieves both (definition + import), so full impact recall.
    assert res["impact_symbols"] == ["list_sessions_by_date_range"]
    assert res["impact_ground_truth_count"] == 2
    assert res["impact_recall"] == 1.0


def test_evaluate_task_impact_recall_zero_when_missing(tmp_path):
    root = _tmp_repo(tmp_path)
    task = {
        "id": 2,
        "query": "completely unrelated query words",
        "expected_code": [],
        "expected_docs": [],
        "forbidden": [],
        "impact_symbols": ["list_sessions_by_date_range"],
    }
    res = b.evaluate_task(root, task, now="2026-08-13T00:00:00Z")
    assert res["impact_ground_truth_count"] == 2
    assert res["impact_recall"] == 0.0


def test_score_ranked():
    expected = ["app/svc.py", "tests/test_svc.py"]
    ranked = ["app/svc.py", "app/other.py", "tests/test_svc.py"]
    res = b.score_ranked(expected, ranked)
    assert res["recall_code"] == 1.0
    assert res["recall_at_5"] == 1.0
    assert res["mrr"] == 1.0


def test_run_benchmark_vectors_flag_graceful():
    root = b.Path(__file__).resolve().parents[2]
    report = b.run_benchmark(root, now="2026-08-13T00:00:00Z", include_vectors=True)
    assert "vectors" in report
    vec = report["vectors"]
    # without the optional deps installed, the A/B section must degrade gracefully
    assert isinstance(vec["available"], bool)
    assert "tasks" in vec
    assert len(vec["tasks"]) == len(b.BENCHMARK_TASKS)
    if vec["available"]:
        assert "aggregate" in vec
        assert "mean_recall_at_5" in vec["aggregate"]
    else:
        assert "reason" in vec


def test_run_benchmark_default_has_no_vectors_section():
    root = b.Path(__file__).resolve().parents[2]
    report = b.run_benchmark(root, now="2026-08-13T00:00:00Z")
    assert "vectors" not in report
