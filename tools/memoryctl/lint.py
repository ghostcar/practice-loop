"""memoryctl lint — validate the Memory v2 corpus (MEMORY_SCHEMA.md §16).

Scopes:
- docs/wiki/**/*.md, docs/adr/**/*.md, docs/questions/**/*.md (frontmatter docs);
- knowledge.md at repo root and inside app/** (frontmatter contracts);
- docs/state/FACTS.json + docs/state/NOW.md (generated state).

Checks: schema fields, id uniqueness, kind/status/authority, id patterns,
supersedes consistency, size budgets, denylist, secret patterns, and
generated-state freshness. Exit code 0 = no errors, 1 = errors present.
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .facts import check_facts
from .schemas import (
    DENYLIST_GLOBS,
    FULL_SHA,
    SECRET_PATTERNS,
    load_document,
    validate_document,
)

V2_DOC_GLOBS = (
    "docs/wiki/**/*.md",
    "docs/adr/**/*.md",
    "docs/questions/**/*.md",
    "knowledge.md",
    "app/**/knowledge.md",
)


@dataclass
class Issue:
    level: str  # error | warning | info
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.message}"


@dataclass
class LintResult:
    issues: list[Issue] = field(default_factory=list)

    def add(self, level: str, message: str) -> None:
        self.issues.append(Issue(level, message))

    @property
    def has_errors(self) -> bool:
        return any(i.level == "error" for i in self.issues)


def _iter_v2_docs(root: Path) -> list[Path]:
    found: list[Path] = []
    for glob in V2_DOC_GLOBS:
        if "*" in glob:
            found.extend(sorted(root.glob(glob)))
        else:
            p = root / glob
            if p.exists():
                found.append(p)
    return found


def _is_denied(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/")
    for pattern in DENYLIST_GLOBS:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel.lstrip("./"), pattern):
            return True
    return False


def _scan_secrets(text: str, rel: str, result: LintResult) -> None:
    for i, line in enumerate(text.splitlines(), 1):
        for pattern in SECRET_PATTERNS:
            if pattern.search(line):
                result.add("error", f"{rel}:{i}: possible secret/credential pattern ({pattern.pattern[:24]}…)")
                return


def _check_supersedes(docs: list, result: LintResult) -> None:
    ids = {d.meta.get("id") for d in docs if d.has_frontmatter}
    superseded: dict[str, list[str]] = {}
    for d in docs:
        if not d.has_frontmatter:
            continue
        doc_id = d.meta.get("id")
        for ref in d.meta.get("supersedes") or []:
            superseded.setdefault(ref, []).append(doc_id)
            if ref not in ids:
                result.add("error", f"{d.path}: supersedes references unknown id {ref!r}")
        by = d.meta.get("superseded_by")
        if by and by not in ids:
            result.add("error", f"{d.path}: superseded_by references unknown id {by!r}")
    for ref, users in superseded.items():
        for user in users:
            target = next((d for d in docs if d.has_frontmatter and d.meta.get("id") == ref), None)
            if target is not None and target.meta.get("superseded_by") != user:
                result.add(
                    "warning", f"{ref}: supersedes listed by {user} but {ref} does not declare superseded_by={user}"
                )


def _check_size(doc, result: LintResult) -> None:
    kind = doc.meta.get("kind")
    if kind == "knowledge":
        size = len(doc.frontmatter_raw.encode("utf-8")) + len(doc.body.encode("utf-8"))
        if size > 12288:
            result.add("error", f"{doc.path}: knowledge page is {size} B (> 12 KiB limit)")
        elif size > 8192:
            result.add("warning", f"{doc.path}: knowledge page is {size} B (> 8 KiB target)")


def lint(root: Path) -> LintResult:
    result = LintResult()
    docs = [load_document(p) for p in _iter_v2_docs(root)]
    known_ids: set[str] = set()
    frontmatter_docs = []

    for doc in docs:
        rel = doc.path.relative_to(root).as_posix()
        if _is_denied(rel):
            result.add("error", f"{rel}: path is on the denylist")
            continue
        if doc.has_frontmatter:
            frontmatter_docs.append(doc)
            doc_id = doc.meta.get("id")
            # validate against ids of *previous* docs, then register this one
            for err in validate_document(doc, known_ids=known_ids):
                result.add("error", err)
            if isinstance(doc_id, str):
                known_ids.add(doc_id)
            _check_size(doc, result)
        _scan_secrets((doc.frontmatter_raw or "") + "\n" + doc.body, rel, result)

    _check_supersedes(frontmatter_docs, result)

    # Generated state
    facts_path = root / "docs" / "state" / "FACTS.json"
    now_path = root / "docs" / "state" / "NOW.md"
    if facts_path.exists():
        try:
            stored = json.loads(facts_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            result.add("error", f"docs/state/FACTS.json: invalid JSON ({exc})")
            stored = {}
        if stored.get("kind") != "fact_manifest":
            result.add("error", "docs/state/FACTS.json: missing kind=fact_manifest")
        head = stored.get("git", {}).get("head")
        if isinstance(head, str) and not FULL_SHA.match(head):
            result.add("error", f"docs/state/FACTS.json: git.head is not a full SHA ({head!r})")
        ok, msg = check_facts(root)
        if not ok:
            result.add("error", f"docs/state/FACTS.json: {msg}")
    else:
        result.add("warning", "docs/state/FACTS.json missing (run 'memoryctl facts')")

    if now_path.exists():
        now_text = now_path.read_text(encoding="utf-8")
        if "GENERATED by memoryctl facts" not in now_text:
            result.add("error", "docs/state/NOW.md: missing generated banner")
    else:
        result.add("warning", "docs/state/NOW.md missing (run 'memoryctl facts')")

    # Denylist audit over git-tracked files
    proc = subprocess.run(["git", "ls-files"], cwd=str(root), capture_output=True, text=True, timeout=30)
    if proc.returncode == 0:
        for rel in proc.stdout.splitlines():
            if rel.strip() and _is_denied(rel):
                result.add("warning", f"git-tracked path on denylist: {rel}")

    if not frontmatter_docs:
        result.add("info", "no Memory v2 frontmatter documents found yet (M2 will populate docs/wiki|adr|questions)")
    return result


def render(result: LintResult) -> str:
    lines = [str(i) for i in result.issues]
    if not lines:
        lines.append("no issues")
    counts = {"error": 0, "warning": 0, "info": 0}
    for i in result.issues:
        counts[i.level] += 1
    lines.append("")
    lines.append(f"{counts['error']} errors, {counts['warning']} warnings, {counts['info']} info")
    return "\n".join(lines)


def main_lint(root: Path) -> int:
    result = lint(root)
    print(render(result))
    return 1 if result.has_errors else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main_lint(Path.cwd()))
