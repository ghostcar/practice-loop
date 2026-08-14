"""memoryctl benchmark — M3 base retrieval benchmark (CODE_MEMORY_DESIGN.md §12).

Runs the 12 benchmark tasks from `docs/memory-rfc/BENCHMARK_TASKS.md` through the
deterministic exact/lexical `bootstrap` and scores the retrieved sources against
the ground-truth expected sources. Metrics:

- recall@5 — fraction of expected *code* sources found in the top-5 code results;
- recall (code / docs / all) — fraction of expected sources found anywhere;
- MRR — mean reciprocal rank of the first expected-code hit in the ranked list;
- pack_size_bytes — deterministic context pack size (target ≤ 12 KiB);
- extra_reads — retrieved code files that are not in the expected set;
- forbidden_hits — retrieved sources matching a task's forbidden patterns.

Output: `docs/state/BENCHMARK.json` (HEAD-bound, regenerable, deterministic).

Commands:
    python -m tools.memoryctl benchmark
    python -m tools.memoryctl benchmark --json
"""

from __future__ import annotations

import json
import statistics
from fnmatch import fnmatch
from pathlib import Path

from .bootstrap import bootstrap
from .facts import git_branch, git_dirty, git_head, git_head_date

SCHEMA_VERSION = "memory/v2alpha1"
GENERATOR_VERSION = "0.1.0"
REPORT_RELPATH = "docs/state/BENCHMARK.json"

# Admission thresholds for making a retrieval tool *mandatory* (RFC §7/§12).
# Informational for the base fallback: the base is the exact/lexical floor that
# every pilot must beat, not a candidate for mandatory dependency itself.
THRESHOLDS = {
    "recall_at_5_min": 0.9,
    "pack_size_max_bytes": 12288,
}

# ---------------------------------------------------------------------------
# Ground truth (docs/memory-rfc/BENCHMARK_TASKS.md, owner-authored)
# ---------------------------------------------------------------------------

# Expected paths are repo-relative POSIX paths; a `*`/`?` pattern is matched
# with fnmatch. expected_code lives under app|tests|alembic (search_code scope);
# expected_docs covers everything else (L0/L1 corpus + legacy docs not yet split).
BENCHMARK_TASKS: list[dict] = [
    {
        "id": 1,
        "query": "Что происходит при POST /api/v2/locktimer/slot-occurrences/{id}/open? Найди полную цепочку",
        "expected_code": [
            "app/api/locktimer_commands.py",
            "app/locktimer/services/execution.py",
            "app/models/locktimer.py",
            "alembic/versions/*025*",
            "tests/test_locktimer_services.py",
        ],
        "expected_docs": [],
        "forbidden": [],
    },
    {
        "id": 2,
        "query": "Переименовать/изменить сигнатуру list_sessions_by_date_range — найти всех потребителей",
        "expected_code": [
            "app/locktimer/repositories.py",
            "app/api/locktimer_ui.py",
            "app/timeutils.py",
            "tests/test_locktimer_services.py",
            "tests/test_timeutils.py",
        ],
        "expected_docs": [],
        "forbidden": [],
        "notes": (
            "Spec lists app/timeutils.py + tests/test_timeutils.py in the chain, but they hold "
            "local_day_bounds (a dependency of list_sessions_by_date_range), not consumers. "
            "The 3 literal consumers (repositories.py, locktimer_ui.py, test_locktimer_services.py) "
            "were all retrieved."
        ),
        "impact_symbols": ["list_sessions_by_date_range"],
    },
    {
        "id": 3,
        "query": "Границы суток «сегодня» в tz устройства — где считается и как рендерится?",
        "expected_code": [
            "app/timeutils.py",
            "app/main.py",
            "app/api/points/charts.py",
            "app/templates/base.html",
            "app/templates/dashboard_v2.html",
            "tests/test_charts_tz.py",
        ],
        "expected_docs": [],
        "forbidden": [],
    },
    {
        "id": 4,
        "query": "Как работает safety/emergency stop в LockTimer — какие инварианты?",
        "expected_code": [
            "app/locktimer/services/session.py",
            "app/locktimer/domain.py",
            "app/locktimer/enums.py",
            "app/api/locktimer_commands.py",
            "tests/test_locktimer_services.py",
        ],
        "expected_docs": ["PRODUCT_DECISIONS.md", "DOCUMENTATION_MAP.md"],
        "forbidden": [],
        "impact_symbols": ["safety_stop"],
    },
    {
        "id": 5,
        "query": "Граница Social и D/s: что Social хранит и что не хранит про отношения",
        "expected_code": [
            "app/platform/social/models.py",
            "app/platform/social/api/relationships.py",
        ],
        "expected_docs": ["PRODUCT_DECISIONS.md", "memory/DECISIONS.md"],
        "forbidden": [],
    },
    {
        "id": 6,
        "query": "Контракт LLM-провайдера: где шифруется api_key и где гарантированно не светится raw_llm_response",
        "expected_code": [
            "app/encryption.py",
            "app/models/llm_config.py",
            "app/security.py",
            "app/api/llm_configs.py",
            "app/platform/social/adapters.py",
        ],
        "expected_docs": [],
        "forbidden": [],
    },
    {
        "id": 7,
        "query": "Добавить новую кнопку на страницу таймера с переводом EN/RU",
        "expected_code": [
            "app/templates/locktimer/session_detail.html",
            "app/i18n/en.py",
            "app/i18n/ru.py",
            "app/i18n/helpers.py",
        ],
        "expected_docs": [],
        "forbidden": [],
    },
    {
        "id": 8,
        "query": "Сколько сейчас миграций и какая последняя? Есть ли расхождение head?",
        "expected_code": ["alembic/env.py", "alembic/versions/*.py"],
        "expected_docs": ["alembic.ini", "docs/state/FACTS.json"],
        "forbidden": [],
    },
    {
        "id": 9,
        "query": "Какое решение отменило «Timer Core обязан быть семантически нейтральным»?",
        "expected_code": [],
        "expected_docs": ["DOCUMENTATION_MAP.md", "memory/DECISIONS.md"],
        "forbidden": [],
    },
    {
        "id": 10,
        "query": "Реализован ли OCR/LLM верификация кодов по фото?",
        "expected_code": [
            "app/models/media.py",
            "app/services/media.py",
            "app/api/verification.py",
        ],
        "expected_docs": ["memory/OPEN_QUESTIONS.md", "CURRENT_STATE.md"],
        "forbidden": ["ROADMAP.md"],
    },
    {
        "id": 11,
        "query": "Почему /locktimer давал 500 на Postgres и как чинили?",
        "expected_code": [
            "app/locktimer/repositories.py",
            "app/timeutils.py",
            "tests/test_locktimer_services.py",
        ],
        "expected_docs": [],
        "forbidden": [],
        "impact_symbols": ["local_day_bounds"],
    },
    {
        "id": 12,
        "query": "Где тесты на verify_tag и tag violations?",
        "expected_code": [
            "tests/test_locktimer_services.py",
            "app/locktimer/services/tags.py",
            "app/api/locktimer_commands.py",
        ],
        "expected_docs": [],
        "forbidden": [],
    },
]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _pattern_hit(pattern: str, paths: set[str]) -> bool:
    return any(fnmatch(p, pattern) for p in paths)


def _matched(patterns: list[str], paths: set[str]) -> list[str]:
    return [pat for pat in patterns if _pattern_hit(pat, paths)]


def build_impact_ground_truth(root: Path, symbols: list[str]) -> set[str]:
    """All scan-scope files (app/tests/alembic) containing any of ``symbols``.

    This is the *mechanically derived* impact set for a symbol (consumers +
    tests + migrations) — the ground truth an impact-aware retriever (e.g. a
    future code-graph pilot) must find. Independent of the pack contents.
    """
    from .bootstrap import _iter_scan_files

    if not symbols:
        return set()
    ground: set[str] = set()
    for p, rel in _iter_scan_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(s in text for s in symbols):
            ground.add(rel)
    return ground


def evaluate_task(root: Path, task: dict, now: str | None = None) -> dict:
    """Score one task. Returns a metric dict (no pack internals leaked)."""
    query = task["query"]
    session_id = f"benchmark-{task['id']}"
    pack = bootstrap(root, query, session_id=session_id, now=now)

    sources = pack["sources"]
    code_ranked = [s["path"] for s in sources if s.get("retriever") == "lexical"]
    retrieved = {s["path"] for s in sources}
    top5 = set(code_ranked[:5])

    expected_code = task.get("expected_code", [])
    expected_docs = task.get("expected_docs", [])
    forbidden = task.get("forbidden", [])
    total_expected = len(expected_code) + len(expected_docs)

    found_code = _matched(expected_code, set(code_ranked))
    found_docs = _matched(expected_docs, retrieved)
    found_all = found_code + found_docs

    # MRR: rank of the first retrieved path matching any expected_code pattern.
    mrr = 0.0
    for rank, path in enumerate(code_ranked, start=1):
        if any(fnmatch(path, pat) for pat in expected_code):
            mrr = 1.0 / rank
            break

    extra_reads = [p for p in code_ranked if not any(fnmatch(p, pat) for pat in expected_code)]
    forbidden_hits = sorted(p for p in retrieved if any(fnmatch(p, pat) for pat in forbidden))
    missing = [pat for pat in expected_code + expected_docs if not _pattern_hit(pat, retrieved)]

    # Impact recall (STAGE_PLAN Шаг 3): for tasks with impact_symbols, the
    # mechanically derived impact set (all files containing the symbol) is the
    # ground truth — consumers + tests + migrations an impact-aware retriever
    # must find. This is the metric a future code-graph pilot gets compared
    # against (RFC §7/§12 incremental evidence).
    impact_symbols = task.get("impact_symbols", [])
    if impact_symbols:
        ground = build_impact_ground_truth(root, impact_symbols)
        impact_found = ground & retrieved
        impact_recall = len(impact_found) / len(ground) if ground else 1.0
    else:
        ground = set()
        impact_found = set()
        impact_recall = None

    return {
        "id": task["id"],
        "query": query,
        "notes": task.get("notes", ""),
        "expected_code_count": len(expected_code),
        "expected_docs_count": len(expected_docs),
        "recall_at_5": (len(_matched(expected_code, top5)) / len(expected_code)) if expected_code else 1.0,
        "recall_code": (len(found_code) / len(expected_code)) if expected_code else 1.0,
        "recall_docs": (len(found_docs) / len(expected_docs)) if expected_docs else 1.0,
        "recall_all": (len(found_all) / total_expected) if total_expected else 1.0,
        "mrr": mrr,
        "pack_size_bytes": pack["size_bytes"],
        "extra_reads_count": len(extra_reads),
        "extra_reads": extra_reads,
        "forbidden_hits": forbidden_hits,
        "missing": missing,
        "impact_symbols": impact_symbols,
        "impact_ground_truth_count": len(ground),
        "impact_recall": impact_recall,
    }


def score_ranked(expected_code: list[str], ranked: list[str], top_k: int = 5) -> dict:
    """Score a ranked path list against expected code patterns (A/B for vector pilot)."""
    if not expected_code:
        return {"recall_at_5": 1.0, "recall_code": 1.0, "mrr": 0.0}
    topk = set(ranked[:top_k])
    found = _matched(expected_code, set(ranked))
    mrr = 0.0
    for rank, path in enumerate(ranked, start=1):
        if any(fnmatch(path, pat) for pat in expected_code):
            mrr = 1.0 / rank
            break
    return {
        "recall_at_5": len(_matched(expected_code, topk)) / len(expected_code),
        "recall_code": len(found) / len(expected_code),
        "mrr": mrr,
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def run_benchmark(root: Path, now: str | None = None, *, include_vectors: bool = False) -> dict:
    """Run all tasks and produce the HEAD-bound report dict."""
    results = [evaluate_task(root, task, now=now) for task in BENCHMARK_TASKS]

    recall_at_5 = [r["recall_at_5"] for r in results]
    recall_code = [r["recall_code"] for r in results]
    recall_docs = [r["recall_docs"] for r in results]
    recall_all = [r["recall_all"] for r in results]
    mrr = [r["mrr"] for r in results]
    pack_sizes = [r["pack_size_bytes"] for r in results]
    impact_results = [r for r in results if r.get("impact_recall") is not None]

    agg = {
        "mean_recall_at_5": round(_mean(recall_at_5), 4),
        "mean_recall_code": round(_mean(recall_code), 4),
        "mean_recall_docs": round(_mean(recall_docs), 4),
        "mean_recall_all": round(_mean(recall_all), 4),
        "mean_mrr": round(_mean(mrr), 4),
        "median_pack_size_bytes": int(statistics.median(pack_sizes)),
        "max_pack_size_bytes": max(pack_sizes),
        "total_extra_reads": sum(r["extra_reads_count"] for r in results),
        "forbidden_hits": sum(len(r["forbidden_hits"]) for r in results),
        "tasks_full_code_recall": sum(1 for r in results if r["recall_code"] >= 1.0),
        "mean_impact_recall": round(_mean([r["impact_recall"] for r in impact_results]), 4) if impact_results else None,
        "tasks_with_impact": len(impact_results),
    }

    meets = (
        agg["mean_recall_at_5"] >= THRESHOLDS["recall_at_5_min"]
        and agg["max_pack_size_bytes"] <= THRESHOLDS["pack_size_max_bytes"]
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "benchmark_report",
        "generated_at": now or git_head_date(root),
        "generator_version": GENERATOR_VERSION,
        "head": git_head(root),
        "branch": git_branch(root),
        "dirty": git_dirty(root),
        "task_count": len(results),
        "thresholds": THRESHOLDS,
        "meets_admission_thresholds": meets,
        "aggregate": agg,
        "tasks": results,
        "limitations": (
            "expected_docs includes legacy docs (PRODUCT_DECISIONS.md, memory/DECISIONS.md, "
            "memory/OPEN_QUESTIONS.md, CURRENT_STATE.md, alembic.ini) that are outside the current "
            "L0/L1 corpus (knowledge.md + docs/{adr,wiki,questions}) and outside search_code scope "
            "(app|tests|alembic). Doc-recall misses for these reflect the M5 split boundary, not a "
            "retrieval bug. Pack size is measured with a deterministic session id and head-anchored "
            "timestamp."
        ),
    }
    if include_vectors:
        report["vectors"] = run_vectors_ab(root)
    return report


def evaluate_vectors(root: Path, task: dict, *, top_k: int = 5) -> dict:
    """A/B: score the vector pilot against a task's expected code (ADR-069 shadow)."""
    from . import vectors

    available, reason = vectors.is_available()
    expected_code = task.get("expected_code", [])
    entry: dict = {
        "id": task["id"],
        "available": available,
        "expected_code_count": len(expected_code),
    }
    if not available:
        entry["reason"] = reason
        entry["recall_at_5"] = 0.0
        entry["recall_code"] = 0.0
        entry["mrr"] = 0.0
        return entry

    result = vectors.search_code(root, task["query"], limit=top_k)
    entry["stale"] = result.get("stale", False)
    entry["reason"] = result.get("reason", "")
    ranked = vectors.ranked_paths(result)
    entry["ranked"] = ranked
    entry.update(score_ranked(expected_code, ranked, top_k=top_k))
    entry["confirmation_ok"] = sum(1 for r in result.get("results", []) if r.get("confirmation") == "exact-read")
    return entry


def run_vectors_ab(root: Path) -> dict:
    """Vector A/B section (shadow) for the benchmark report; graceful when deps absent."""
    tasks = [evaluate_vectors(root, task) for task in BENCHMARK_TASKS]
    available = any(t.get("available") for t in tasks)
    if not available:
        return {
            "available": False,
            "reason": tasks[0].get("reason", "vector deps not installed"),
            "tasks": tasks,
        }
    recall_at_5 = [t["recall_at_5"] for t in tasks]
    mrr = [t["mrr"] for t in tasks]
    return {
        "available": True,
        "aggregate": {
            "mean_recall_at_5": round(_mean(recall_at_5), 4),
            "mean_mrr": round(_mean(mrr), 4),
            "tasks_full_code_recall": sum(1 for t in tasks if t.get("recall_code", 0.0) >= 1.0),
        },
        "tasks": tasks,
    }


def write_report(root: Path, report: dict) -> Path:
    state_dir = root / "docs" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "BENCHMARK.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def render_summary(report: dict) -> str:
    agg = report["aggregate"]
    t = report["thresholds"]
    lines = [
        f"head={report['head']} branch={report['branch']} dirty={report['dirty']}",
        f"tasks={report['task_count']}",
        f"recall@5 (code)      : {agg['mean_recall_at_5']:.2f}  (threshold >= {t['recall_at_5_min']})",
        f"recall code / docs / all: {agg['mean_recall_code']:.2f} / "
        f"{agg['mean_recall_docs']:.2f} / {agg['mean_recall_all']:.2f}",
        f"MRR (code)           : {agg['mean_mrr']:.3f}",
        f"pack size median/max : {agg['median_pack_size_bytes']} / "
        f"{agg['max_pack_size_bytes']} B  (limit <= {t['pack_size_max_bytes']})",
        f"extra reads (total)  : {agg['total_extra_reads']}",
        f"forbidden hits       : {agg['forbidden_hits']}",
        f"full code recall in {agg['tasks_full_code_recall']}/{report['task_count']} tasks",
        f"impact recall ({agg['tasks_with_impact']} impact tasks): "
        f"{agg['mean_impact_recall'] if agg['mean_impact_recall'] is not None else 'n/a'}",
        f"meets admission thresholds: {report['meets_admission_thresholds']}",
    ]
    vec = report.get("vectors")
    if vec is not None:
        if vec.get("available"):
            va = vec["aggregate"]
            base_r5 = agg["mean_recall_at_5"]
            vec_r5 = va["mean_recall_at_5"]
            delta = vec_r5 - base_r5
            lines += [
                "",
                "vectors (ADR-069 shadow A/B):",
                f"  recall@5  base {base_r5:.2f} -> vector {vec_r5:.2f}  (delta {delta:+.2f})",
                f"  MRR       base {agg['mean_mrr']:.3f} -> vector {va['mean_mrr']:.3f}",
                f"  full code recall in {va['tasks_full_code_recall']}/{report['task_count']} tasks",
            ]
        else:
            lines += ["", f"vectors unavailable: {vec.get('reason')}"]
    return "\n".join(lines)
