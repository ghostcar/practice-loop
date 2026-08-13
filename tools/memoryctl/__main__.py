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
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
