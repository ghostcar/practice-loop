"""memoryctl sentinel — verify a fresh preflight sentinel (MEMORY_ARCHITECTURE.md §8, rail 6).

A valid preflight produces `.agent-runtime/session.json` (the sentinel). Before a
commit the agent must prove a *fresh* preflight exists:

- the sentinel parses and declares ``kind == session_sentinel``;
- ``status`` is ``ready`` (or acceptable ``degraded``);
- ``start_head`` is an ancestor of (or equal to) the current HEAD — a later linear
  commit of the agent's own work does not invalidate it, but a diverged/unrelated
  HEAD does;
- ``pack_hash`` matches a recomputed hash of ``context-pack.json`` (integrity);
- optional TTL: ``created_at`` is within the window.

This is the local pre-commit gate; CI ``memory-lint`` stays informational.

Commands:
    python -m tools.memoryctl sentinel [--ttl-hours N]
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA_VERSION = "memory/v2alpha1"
RUNTIME_DIR = ".agent-runtime"
SENTINEL_RELPATH = f"{RUNTIME_DIR}/session.json"
PACK_RELPATH = f"{RUNTIME_DIR}/context-pack.json"

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
PACK_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T")

_VALID_STATUSES = {"ready", "degraded"}


def _run(cmd: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover - env dependent
        return 127, str(exc)


def git_head_exact(root: Path) -> str | None:
    code, out = _run(["git", "rev-parse", "HEAD"], root)
    return out if code == 0 and FULL_SHA.match(out) else None


def _is_ancestor(ancestor: str, head: str, root: Path) -> bool:
    if ancestor == head:
        return True
    code, _ = _run(["git", "merge-base", "--is-ancestor", ancestor, head], root)
    return code == 0


def _pack_hash(pack_path: Path) -> str | None:
    try:
        raw = pack_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def load_sentinel(root: Path) -> dict | None:
    path = root / SENTINEL_RELPATH
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def check_sentinel(root: Path, ttl_hours: float | None = None, now: str | None = None) -> tuple[bool, str]:
    """Return (ok, message). Fails closed on any malformed/stale/missing state."""
    head = git_head_exact(root)
    if head is None:
        return False, "sentinel check requires a git HEAD (not a bare/empty repo)"

    sentinel = load_sentinel(root)
    if sentinel is None:
        return False, f"no preflight sentinel at {SENTINEL_RELPATH} — run 'memoryctl bootstrap --task ...'"

    if sentinel.get("kind") != "session_sentinel":
        return False, f"{SENTINEL_RELPATH}: kind is not 'session_sentinel'"
    if sentinel.get("schema_version") != SCHEMA_VERSION:
        return False, f"{SENTINEL_RELPATH}: unsupported schema_version {sentinel.get('schema_version')!r}"

    status = sentinel.get("status")
    if status not in _VALID_STATUSES:
        return False, f"{SENTINEL_RELPATH}: status {status!r} is not ready/degraded (preflight was blocked)"

    start_head = sentinel.get("start_head")
    if not isinstance(start_head, str) or not FULL_SHA.match(start_head):
        return False, f"{SENTINEL_RELPATH}: start_head is not a full SHA ({start_head!r})"
    if not _is_ancestor(start_head, head, root):
        return False, (
            f"{SENTINEL_RELPATH}: stale preflight — start_head {start_head[:12]} is not an ancestor "
            f"of current HEAD {head[:12]}"
        )

    # integrity: pack hash must match the on-disk context pack
    pack_path = root / PACK_RELPATH
    if not pack_path.exists():
        return False, f"{PACK_RELPATH} missing — sentinel cannot be verified"
    recomputed = _pack_hash(pack_path)
    if sentinel.get("pack_hash") != recomputed:
        return False, f"{SENTINEL_RELPATH}: pack_hash mismatch (context pack was modified after preflight)"

    created_at = sentinel.get("created_at")
    if not isinstance(created_at, str) or not ISO_TS.match(created_at):
        return False, f"{SENTINEL_RELPATH}: missing/invalid created_at ({created_at!r})"
    if ttl_hours is not None:
        created = _parse_iso(created_at)
        ref = _parse_iso(now) if now else datetime.now(UTC)
        if created is None or ref is None or (ref - created) > timedelta(hours=ttl_hours):
            return False, f"{SENTINEL_RELPATH}: preflight is older than TTL ({ttl_hours}h)"

    return True, f"sentinel ready: preflight at {start_head[:12]} covers HEAD {head[:12]}"


def main_sentinel(root: Path, ttl_hours: float | None = None) -> int:
    ok, msg = check_sentinel(root, ttl_hours=ttl_hours)
    print(("OK: " if ok else "FAIL: ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main_sentinel(Path.cwd()))
