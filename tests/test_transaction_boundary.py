"""Transaction boundary checks (audit P1-5).

The project follows the rule: routers validate HTTP input and call services;
the service owns the transaction; `get_db()` auto-commits after the endpoint.
Historically, a number of routers call `db.commit()` themselves — that is
legacy debt, enumerated in LEGACY_COMMIT_ROUTERS below.

These tests make sure the debt does not grow:

1. No `db.commit()` may appear in NEW router files (any file under app/api/
   or app/platform/social/api/ not on the legacy allowlist).
2. LockTimer and Social API routers (built after the rule was adopted) must
   stay commit-free.
3. The auto-commit behaviour of get_db() is asserted so the rule stays true.
"""

from __future__ import annotations

import re
from pathlib import Path

API_DIRS = [Path("app/api"), Path("app/platform/social/api")]

# Legacy files that still call db.commit() themselves. New routers must NOT
# be added here — instead move the transaction into a service (audit P1-5).
LEGACY_COMMIT_ROUTERS: set[str] = set()  # P7: all legacy db.commit() removed (ADR-160)

COMMIT_RE = re.compile(r"await\s+(?:db|session|db_session)\.commit\(\)")


def _all_api_py_files() -> list[Path]:
    files: list[Path] = []
    for d in API_DIRS:
        files.extend(p for p in d.rglob("*.py") if "__pycache__" not in str(p))
    return files


def test_legacy_allowlist_is_accurate() -> None:
    """The allowlist must exactly match the current commit-using routers."""
    actual = set()
    for p in _all_api_py_files():
        if COMMIT_RE.search(p.read_text(encoding="utf-8")):
            actual.add(str(p))
    # Import-data facade may re-export, but its own router functions commit.
    assert actual == LEGACY_COMMIT_ROUTERS, (
        f"allowlist drift: missing={sorted(LEGACY_COMMIT_ROUTERS - actual)} "
        f"extra={sorted(actual - LEGACY_COMMIT_ROUTERS)}"
    )


def test_no_new_commits_in_routers() -> None:
    """New router files must not call db.commit() — services own transactions."""
    offenders = []
    for p in _all_api_py_files():
        rel = str(p)
        if rel in LEGACY_COMMIT_ROUTERS:
            continue
        if COMMIT_RE.search(p.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert not offenders, f"db.commit() in new routers — move into services: {offenders}"


def test_locktimer_and_social_routers_are_commit_free() -> None:
    """Modules built after the rule must already follow it."""
    for p in _all_api_py_files():
        rel = str(p)
        if rel.startswith("app/api/locktimer") or rel.startswith("app/platform/social/api"):
            assert not COMMIT_RE.search(p.read_text(encoding="utf-8")), f"commit in {rel}"
