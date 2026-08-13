"""memoryctl impact — advisory check that working-tree changes are covered by preflight.

Rail 5 (MEMORY_ARCHITECTURE.md §8): before completing a significant change the
agent verifies that the files it touched were part of the preflight's impact
frontier (tests/migrations/call sites) or are additions/docs/config. Changes to
existing *code* files outside the frontier are reported as ``out_of_scope`` — a
signal to re-run ``memoryctl bootstrap``.

This is advisory: it never rewrites anything and its exit code only reflects
whether a preflight pack exists (0 = check ran, 1 = no pack to check against).

Commands:
    python -m tools.memoryctl impact
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

RUNTIME_DIR = ".agent-runtime"
PACK_RELPATH = f"{RUNTIME_DIR}/context-pack.json"

# Paths always allowed to change without preflight coverage (docs/config/generated).
_ALWAYS_ALLOWED_PREFIXES = (
    "memory/",
    "docs/",
    ".github/",
    ".githooks/",
    ".agents/",
    "bin/",
)
_ALWAYS_ALLOWED_SUFFIXES = (".md",)

# Paths treated as "code" (subject to impact coverage).
_CODE_PREFIXES = ("app/", "tests/", "alembic/", "tools/")
_CODE_SUFFIXES = (".py", ".html", ".js", ".ts", ".css", ".toml")


def _run(cmd: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip("\n")
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover - env dependent
        return 127, str(exc)


def _is_always_allowed(rel: str) -> bool:
    return rel.startswith(_ALWAYS_ALLOWED_PREFIXES) or rel.endswith(_ALWAYS_ALLOWED_SUFFIXES)


def _is_code(rel: str) -> bool:
    return rel.startswith(_CODE_PREFIXES) or rel.endswith(_CODE_SUFFIXES)


def changed_paths(root: Path) -> list[tuple[str, str]]:
    """Return sorted [(rel_path, kind)] from git status; kind in {added, modified, deleted}."""
    code, out = _run(["git", "status", "--porcelain=v1"], root)
    if code != 0:
        return []
    changes: list[tuple[str, str]] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        path = line[3:].strip()
        if " -> " in path:  # rename: take the new path
            path = path.split(" -> ", 1)[1]
        if not path:
            continue
        if xy == "??" or "A" in xy:
            kind = "added"
        elif "D" in xy:
            kind = "deleted"
        else:
            kind = "modified"
        changes.append((path, kind))
    changes.sort(key=lambda c: c[0])
    return changes


def load_pack(root: Path) -> dict | None:
    path = root / PACK_RELPATH
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def check_impact(root: Path) -> dict:
    """Compare working-tree changes against the last preflight impact frontier."""
    pack = load_pack(root)
    if pack is None:
        return {"has_pack": False, "changed": [], "in_scope": [], "out_of_scope": [], "new_files": [], "notes": []}

    frontier = pack.get("impact_frontier") or {}
    covered = set(frontier.get("tests") or [])
    covered |= set(frontier.get("migrations") or [])
    covered |= set(frontier.get("call_sites") or [])

    changes = changed_paths(root)
    in_scope: list[str] = []
    out_of_scope: list[str] = []
    new_files: list[str] = []
    notes: list[str] = []

    for rel, kind in changes:
        if _is_always_allowed(rel):
            in_scope.append(rel)
            continue
        if kind == "added" and not _is_code(rel):
            in_scope.append(rel)
            continue
        if _is_code(rel):
            if kind == "added":
                new_files.append(rel)
            elif rel in covered:
                in_scope.append(rel)
            else:
                out_of_scope.append(rel)
        else:
            # non-code, non-doc change (e.g. binary/config) — informational
            in_scope.append(rel)

    if out_of_scope:
        notes.append(
            f"{len(out_of_scope)} existing code file(s) changed outside the preflight impact "
            "frontier — consider re-running 'memoryctl bootstrap --task ...'"
        )
    if not pack.get("impact_frontier"):
        notes.append("preflight pack has no impact_frontier — coverage check is inconclusive")

    return {
        "has_pack": True,
        "changed": [c[0] for c in changes],
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "new_files": new_files,
        "notes": notes,
    }


def render(report: dict) -> str:
    if not report["has_pack"]:
        return "FAIL: no preflight pack at .agent-runtime/context-pack.json — run 'memoryctl bootstrap --task ...'"
    lines = [
        f"changed files: {len(report['changed'])}",
        f"  in-scope      : {len(report['in_scope'])}",
        f"  new files     : {len(report['new_files'])}",
        f"  out-of-scope  : {len(report['out_of_scope'])}",
    ]
    for p in report["out_of_scope"]:
        lines.append(f"    ! {p}")
    for n in report["notes"]:
        lines.append(f"  note: {n}")
    return "\n".join(lines)


def main_impact(root: Path) -> int:
    report = check_impact(root)
    print(render(report))
    return 0 if report["has_pack"] else 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main_impact(Path.cwd()))
