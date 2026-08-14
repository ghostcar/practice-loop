"""memoryctl CLI — python -m tools.memoryctl <command>."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    """Walk up to the directory containing .git."""
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return cur


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memoryctl", description="Practice Loop Memory v2 tooling")
    parser.add_argument("--root", type=Path, default=None, help="repo root (default: nearest dir with .git)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inventory", help="read-only baseline inventory")
    sub.add_parser("lint", help="validate Memory v2 corpus and generated state")
    facts_p = sub.add_parser("facts", help="generate docs/state/FACTS.json + NOW.md")
    facts_p.add_argument("--check", action="store_true", help="verify freshness without writing")
    adr = sub.add_parser("adr", help="split legacy DECISIONS.md into docs/adr/")
    adr_sub = adr.add_subparsers(dest="adr_command", required=True)
    adr_sub.add_parser("compile", help="generate docs/adr/ADR-NNN.md + README.md")
    adr_sub.add_parser("check", help="bidirectional verification (no writes)")

    boot = sub.add_parser("bootstrap", help="build a context pack + sentinel for a task (M3 base)")
    boot.add_argument("--task", required=True, help="task description")
    boot.add_argument(
        "--runtime-dir", default="bootstrap.RUNTIME_DIR", help="local runtime dir (default: .agent-runtime)"
    )
    boot.add_argument("--session-id", default=None, help="override session id (for reproducible runs)")
    boot.add_argument("--limit", type=int, default=20, help="max code results (default: 20)")

    bench = sub.add_parser("benchmark", help="run the M3 base retrieval benchmark (writes docs/state/BENCHMARK.json)")
    bench.add_argument("--json", action="store_true", help="print the full report JSON to stdout")
    bench.add_argument("--vectors", action="store_true", help="include the vector pilot A/B (ADR-069 shadow)")

    idx = sub.add_parser("index-code", help="build the vector code index (ADR-069, optional 'memory' deps)")
    idx.add_argument(
        "--mode",
        default="full",
        choices=["full", "incremental", "check", "shadow", "rebuild"],
        help="index mode (default: full)",
    )

    sc = sub.add_parser("search-code", help="hybrid dense+lexical code search (ADR-069)")
    sc.add_argument("--query", required=True, help="task/query text")
    sc.add_argument("--limit", type=int, default=20, help="max results (default: 20)")

    sent = sub.add_parser("sentinel", help="verify a fresh preflight sentinel (.agent-runtime/session.json)")
    sent.add_argument("--ttl-hours", type=float, default=None, help="optional max age of the preflight in hours")

    sub.add_parser("impact", help="advisory check: working-tree changes vs last preflight impact frontier")

    args = parser.parse_args(argv)
    root = args.root or find_repo_root(Path.cwd())

    if args.command == "inventory":
        from . import inventory as inv_mod

        print(inv_mod.inventory(root, as_json=False))
        return 0
    if args.command == "lint":
        from . import lint as lint_mod

        return lint_mod.main_lint(root)
    if args.command == "facts":
        from . import facts as facts_mod

        if args.check:
            ok, msg = facts_mod.check_facts(root)
            print(msg)
            return 0 if ok else 1
        facts = facts_mod.collect_facts(root)
        json_path, now_path = facts_mod.write_facts(root, facts)
        print(f"wrote {json_path.relative_to(root)} and {now_path.relative_to(root)}")
        return 0
    if args.command == "adr":
        from . import adr as adr_mod

        if args.adr_command == "compile":
            nums = adr_mod.compile_adrs(root)
            print(f"wrote {len(nums)} ADR files + docs/adr/README.md")
            return 0
        ok, msgs = adr_mod.check_bidirectional(root)
        for m in msgs:
            print(m)
        return 0 if ok else 1
    if args.command == "bootstrap":
        from . import bootstrap as boot_mod

        runtime_dir = ".agent-runtime" if args.runtime_dir == "bootstrap.RUNTIME_DIR" else args.runtime_dir
        pack, pack_path, sentinel_path = boot_mod.run_bootstrap(
            root, args.task, session_id=args.session_id, runtime_dir=runtime_dir
        )
        imp = pack["impact_frontier"]
        print(f"mode={pack['mode']} head={pack['start_head']} branch={pack['branch']} dirty={pack['dirty']}")
        print(f"classification={pack['classification']}")
        print(
            f"sources={len(pack['sources'])} "
            f"(tests={len(imp['tests'])} migrations={len(imp['migrations'])} call_sites={len(imp['call_sites'])})"
        )
        for r in pack["risks"]:
            print(f"  risk: {r}")
        for c in pack["required_checks"]:
            print(f"  check: {c}")
        try:
            pp = str(pack_path.relative_to(root))
            sp = str(sentinel_path.relative_to(root))
        except ValueError:
            pp, sp = str(pack_path), str(sentinel_path)
        print(f"wrote {pp} and {sp} ({pack['size_bytes']} B)")
        return 0 if pack["status"] == "ready" else 1
    if args.command == "benchmark":
        import json as _json

        from . import benchmark as bench_mod

        report = bench_mod.run_benchmark(root, include_vectors=args.vectors)
        out_path = bench_mod.write_report(root, report)
        if args.json:
            print(_json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        else:
            print(bench_mod.render_summary(report))
            print(f"wrote {out_path.relative_to(root)}")
        return 0
    if args.command == "index-code":
        from . import vectors as vec_mod

        info = vec_mod.index_code(root, mode=args.mode)
        print(vec_mod.render_index_result(info))
        return 0 if info.get("status") == "ready" else 1
    if args.command == "search-code":
        from . import vectors as vec_mod

        result = vec_mod.search_code(root, args.query, limit=args.limit)
        if not result.get("available"):
            print(f"vectors unavailable: {result.get('reason')}")
            return 1
        if result.get("stale"):
            print(f"index stale: {result.get('reason')}")
            return 1
        for r in result["results"]:
            print(
                f"{r['fused_score']:.6f}  {r['path']}  [{r['unit_kind']}] {r['symbol']}  "
                f"({', '.join(r['matched_by'])}, {r['confirmation']})"
            )
        return 0
    if args.command == "sentinel":
        from . import sentinel as sentinel_mod

        return sentinel_mod.main_sentinel(root, ttl_hours=args.ttl_hours)
    if args.command == "impact":
        from . import impact as impact_mod

        return impact_mod.main_impact(root)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
