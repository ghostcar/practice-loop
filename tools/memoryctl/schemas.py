"""Memory v2 schema — frontmatter parsing and validation (MEMORY_SCHEMA.md).

Stdlib-only implementation of the *constrained* YAML subset used by canonical
Memory v2 documents:

- flat scalars:  ``key: value`` (strings, ints, bools, ``null``, quoted);
- lists of scalars: ``key:`` followed by ``  - item`` lines;
- lists of objects: ``key:`` followed by ``  - field: value`` blocks.

Anything outside this subset raises ``ParseError`` so ``memoryctl lint`` reports
a clear error instead of silently mis-parsing a document.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "memory/v2alpha1"

# kind -> allowed statuses (MEMORY_SCHEMA.md §3)
KIND_STATUSES: dict[str, tuple[str, ...]] = {
    "contract": ("draft", "active", "superseded", "archived"),
    "knowledge": ("draft", "active", "superseded", "archived"),
    "adr": ("proposed", "accepted", "rejected", "superseded"),
    "question": ("open", "blocked", "answered", "cancelled"),
    "evidence": ("current", "stale", "archived"),
    "episode_summary": ("draft", "reviewed", "archived"),
}

AUTHORITIES = ("normative", "technical", "factual", "derived", "historical")

# kind -> required fields (base set + per-kind extras)
BASE_REQUIRED = (
    "schema_version",
    "id",
    "kind",
    "title",
    "status",
    "authority",
    "owners",
    "scope",
    "source_refs",
    "last_verified_at",
    "last_verified_commit",
    "review_on",
)
KIND_REQUIRED: dict[str, tuple[str, ...]] = {
    "adr": ("decision_type", "deciders", "accepted_at", "supersedes", "superseded_by"),
    "question": ("blocking", "decision_deadline", "options", "default_if_no_decision"),
    "episode_summary": (
        "start_commit",
        "end_commit",
        "changed_paths",
        "checks",
        "knowledge_candidates",
        "adr_candidates",
        "redaction_status",
    ),
}

ADECISION_TYPES = ("technical", "product", "safety", "data")

ID_PATTERNS = {
    "knowledge": re.compile(r"^K-[A-Z0-9][A-Z0-9-]*$"),
    "contract": re.compile(r"^C-[A-Z0-9][A-Z0-9-]*$"),
    "adr": re.compile(r"^ADR-\d{3,}$"),
    "question": re.compile(r"^(PQ-\d{3,}|EQ-\d{4,})$"),
    "evidence": re.compile(r"^E-\d{8}-[A-Z0-9-]+$"),
    "episode_summary": re.compile(r"^S-\d{8}-[A-Z0-9]+$"),
}

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

# Denylist (MEMORY_SCHEMA.md §15) — gitignore-style globs
DENYLIST_GLOBS = (
    ".env*",
    ".agent-runtime/**",
    ".memory-local/**",
    "uploads/**",
    "examples/**",
    "**/*.db",
    "**/*.sqlite*",
    "**/*.log",
    "**/*dump*",
    "**/*backup*",
    "**/raw_llm_response*",
    "app/static/fonts/**",
    "app/static/tailwindcss.js",
    "app/static/chart.umd.min.js",
    "app/static/htmx.min.js",
)

# Tracked-secret denylist — a git-tracked file matching these indicates a genuine
# secret/private-data leak (should never be committed). Narrower than DENYLIST_GLOBS:
# vendored assets (fonts, minified JS) are excluded from the index but are NOT
# secrets, so they must not trigger the tracked-secret warning (audit P2-4).
SECRET_DENYLIST_GLOBS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "uploads/**",
    "*.db",
    "*.sqlite*",
    "*.log",
    "*dump*",
    "*backup*",
    "*raw_llm_response*",
)

# Allowlist — explicit, provenance-backed exceptions to SECRET_DENYLIST_GLOBS.
# Never weaken the secret denylist without a security ADR; every entry carries a reason.
ALLOWLIST_GLOBS = (
    (
        ".env.example",
        "sanitized template, no real secrets (pre_deploy_check scans for real ones)",
    ),
    (
        "scripts/backup_prod.sh",
        "backup automation documented by ADR-186; credentials are read from the runtime environment",
    ),
)


def _match_glob(rel_path: str, glob: str) -> bool:
    rel = rel_path.replace("\\", "/")
    return fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(rel.lstrip("./"), glob)


def is_denied(rel_path: str) -> bool:
    """Index policy: True if rel_path must not be embedded/indexed/read by scanners."""
    return any(_match_glob(rel_path, g) for g in DENYLIST_GLOBS)


def is_tracked_secret(rel_path: str) -> bool:
    """Security lint: True if a *tracked* rel_path is a genuine secret/private leak."""
    if not any(_match_glob(rel_path, g) for g in SECRET_DENYLIST_GLOBS):
        return False
    return not any(_match_glob(rel_path, g) for g, _reason in ALLOWLIST_GLOBS)


# High-signal secret patterns (false-positive safe; real scan is pre_deploy_check)
SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)(sk|pk|ghp|gho|ghu|ghs)_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)password\s*=\s*['\"][^'\"]{6,}"),
    re.compile(r"(?i)(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)"),
    re.compile(r"(?i)jwt[_a-z]*\s*=\s*['\"][A-Za-z0-9_.\-]{32,}"),
)


class ParseError(ValueError):
    """Frontmatter could not be parsed with the supported YAML subset."""


@dataclass
class Document:
    """A parsed canonical document with its frontmatter metadata."""

    path: Path
    meta: dict
    body: str
    frontmatter_raw: str | None
    has_frontmatter: bool = False


def _strip_comment(line: str) -> str:
    # Remove trailing ` # comment` outside quotes (naive but adequate for linting).
    out: list[str] = []
    in_quote: str | None = None
    for ch in line:
        if in_quote:
            out.append(ch)
            if ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
            out.append(ch)
        elif ch == "#" and (not out or out[-1].isspace()):
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _parse_scalar(raw: str):
    raw = raw.strip()
    if raw == "" or raw.lower() == "null":
        return None
    if raw == "~":
        return None
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1].replace('\\"', '"')
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1].replace("''", "'")
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    # ints only when unambiguous — leading zeros are kept as strings (e.g. "007")
    if re.fullmatch(r"-?\d+", raw) and not (raw.startswith("0") and len(raw) > 1):
        return int(raw)
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if inner == "":
            return []
        return [_parse_scalar(x) for x in inner.split(",")]
    # bare scalar — strip trailing comma if list-inline
    return raw


@dataclass
class _Block:
    indent: int
    text: str  # raw line (without indentation)
    lineno: int


def _parse_frontmatter(raw: str) -> dict:
    """Parse the YAML-subset frontmatter body into a dict."""
    lines = raw.splitlines()
    blocks: list[_Block] = []
    for i, line in enumerate(lines):
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("\t"):
            raise ParseError(f"line {i + 1}: tabs are not allowed in frontmatter indentation")
        indent = len(line) - len(line.lstrip(" "))
        blocks.append(_Block(indent, _strip_comment(line[indent:]), i + 1))

    def parse_block(idx: int, indent: int) -> tuple[dict | None, int]:
        """Parse a mapping starting at blocks[idx] (expected indent level)."""
        if idx >= len(blocks):
            return None, idx
        if blocks[idx].indent != indent:
            return None, idx
        result: dict = {}
        while idx < len(blocks):
            b = blocks[idx]
            if b.indent < indent:
                break
            if b.indent > indent:
                raise ParseError(f"line {b.lineno}: unexpected indentation {b.indent} (expected {indent})")
            if not b.text.startswith("-") and ":" not in b.text:
                raise ParseError(f"line {b.lineno}: expected 'key:' but got {b.text!r}")
            if b.text.startswith("- "):
                raise ParseError(f"line {b.lineno}: unexpected list item at mapping level")
            key, sep, value = b.text.partition(":")
            key = key.strip()
            if not sep:
                raise ParseError(f"line {b.lineno}: missing ':' after key {key!r}")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ParseError(f"line {b.lineno}: invalid key {key!r}")
            rest = value.strip()
            if rest == "":
                # value is nested block: list or object
                if idx + 1 < len(blocks) and blocks[idx + 1].indent > indent:
                    nxt = blocks[idx + 1]
                    if nxt.text.startswith("- "):
                        # list of scalars or list of objects
                        items: list = []
                        j = idx + 1
                        while j < len(blocks) and blocks[j].indent > indent and blocks[j].text.startswith("- "):
                            item_text = blocks[j].text[2:].strip()
                            if ":" in item_text and "://" not in item_text and not item_text.startswith(('"', "'")):
                                # object item — parse its fields
                                obj, j = parse_object_item(j + 1, blocks[j].indent + 2, item_text)
                                items.append(obj)
                            else:
                                items.append(_parse_scalar(item_text))
                                j += 1
                        idx = j
                        result[key] = items
                        continue
                    # nested object
                    obj, idx = parse_block(idx + 1, nxt.indent)
                    result[key] = obj or {}
                    continue
                result[key] = {}
                idx += 1
                continue
            result[key] = _parse_scalar(rest)
            idx += 1
        return result, idx

    def parse_object_item(idx: int, indent: int, first_line: str) -> tuple[dict, int]:
        """Parse a single object in a list, given its first 'key: value' fragment."""
        obj: dict = {}
        key, _, value = first_line.partition(":")
        key = key.strip()
        if value.strip():
            obj[key] = _parse_scalar(value.strip())
        else:
            obj[key] = {}
        while idx < len(blocks) and blocks[idx].indent >= indent:
            b = blocks[idx]
            if b.indent > indent:
                raise ParseError(f"line {b.lineno}: unexpected nesting inside list item")
            if b.indent == indent and not b.text.startswith("-"):
                k2, _, v2 = b.text.partition(":")
                k2 = k2.strip()
                if v2.strip():
                    obj[k2] = _parse_scalar(v2.strip())
                else:
                    obj[k2] = {}
                idx += 1
                continue
            break
        return obj, idx

    meta, _ = parse_block(0, 0)
    return meta or {}


def split_frontmatter(text: str) -> tuple[str | None, dict, str]:
    """Split file text into (frontmatter_raw, meta, body).

    Returns (None, {}, text) when the file has no frontmatter.
    """
    if not text.startswith("---"):
        return None, {}, text
    lines = text.splitlines(keepends=True)
    # find closing ---
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise ParseError("frontmatter block is not closed (missing trailing '---')")
    raw = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    return "---\n" + raw + "---\n", _parse_frontmatter(raw), body


def load_document(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    fm_raw, meta, body = split_frontmatter(text)
    return Document(path=path, meta=meta, body=body, frontmatter_raw=fm_raw, has_frontmatter=fm_raw is not None)


def required_fields(kind: str) -> tuple[str, ...]:
    return BASE_REQUIRED + KIND_REQUIRED.get(kind, ())


def validate_document(doc: Document, known_ids: set[str] | None = None) -> list[str]:
    """Return a list of validation errors for one document (empty = valid).

    Semantic checks (supersedes graph, dangling source paths) live in lint.py;
    this validates the schema contract from MEMORY_SCHEMA.md.
    """
    errors: list[str] = []
    known_ids = known_ids or set()
    meta = doc.meta
    if not doc.has_frontmatter:
        return errors  # non-v2 markdown is not in scope

    kind = meta.get("kind")
    if not isinstance(kind, str) or kind not in KIND_STATUSES:
        errors.append(f"{doc.path}: unknown kind {kind!r}")
        return errors

    for field_name in required_fields(kind):
        if field_name not in meta:
            errors.append(f"{doc.path}: missing required field '{field_name}'")

    status = meta.get("status")
    if status not in KIND_STATUSES[kind]:
        errors.append(f"{doc.path}: invalid status {status!r} for kind {kind!r}")

    authority = meta.get("authority")
    if authority not in AUTHORITIES:
        errors.append(f"{doc.path}: invalid authority {authority!r}")

    if meta.get("schema_version") not in (None, SCHEMA_VERSION):
        errors.append(f"{doc.path}: unsupported schema_version {meta.get('schema_version')!r}")

    doc_id = meta.get("id")
    if isinstance(doc_id, str):
        pattern = ID_PATTERNS.get(kind)
        if pattern and not pattern.match(doc_id):
            errors.append(f"{doc.path}: id {doc_id!r} does not match pattern for kind {kind!r}")
        if doc_id in known_ids:
            errors.append(f"{doc.path}: duplicate id {doc_id!r}")
    else:
        errors.append(f"{doc.path}: missing string 'id'")

    # Authority rules
    if (
        authority == "normative"
        and not (kind == "adr" and status == "accepted")
        and not (kind == "contract" and status == "active")
    ):
        errors.append(f"{doc.path}: authority=normative allowed only for accepted adr / active contract")
    if authority == "derived" and status in ("active", "accepted") and not meta.get("source_refs"):
        errors.append(f"{doc.path}: active/accepted derived page must have source_refs")

    # Commit freshness
    verified_commit = meta.get("last_verified_commit")
    if status in ("active", "accepted") and isinstance(verified_commit, str) and not FULL_SHA.match(verified_commit):
        errors.append(f"{doc.path}: last_verified_commit must be a full 40-hex SHA (got {verified_commit!r})")
    if status in ("active", "accepted") and verified_commit is None:
        errors.append(f"{doc.path}: last_verified_commit required for {status}")

    # ADR-specific
    if kind == "adr":
        if status == "accepted" and not meta.get("accepted_at"):
            errors.append(f"{doc.path}: accepted adr requires accepted_at")
        if status == "accepted" and not meta.get("deciders"):
            errors.append(f"{doc.path}: accepted adr requires deciders (owner approval)")
        decision_type = meta.get("decision_type")
        if decision_type not in (None,) and decision_type not in ADECISION_TYPES:
            errors.append(f"{doc.path}: invalid decision_type {decision_type!r}")

    # supersedes/superseded_by shape
    for f in ("supersedes",):
        val = meta.get(f)
        if val is not None and not isinstance(val, list):
            errors.append(f"{doc.path}: '{f}' must be a list")
    return errors
