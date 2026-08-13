"""memoryctl bootstrap — deterministic context pack (M3 base, MEMORY_ARCHITECTURE.md §7).

Pure-Python, stdlib-only: classifies a task, selects L0/L1 canonical docs,
runs exact/lexical code search, computes an impact frontier (tests/migrations/
call sites), and writes a context pack + sentinel into a local runtime dir.

The pack *references* sources (id/path/ref/reason) — it never copies long
documents or file bodies. Everything is deterministic given the same task text,
HEAD and session id. This is the "exact fallback" every later retrieval mode
(vectors/graph) degrades to.

Commands:
    python -m tools.memoryctl bootstrap --task "..." [--runtime-dir DIR] [--session-id ID]
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from .facts import git_branch, git_dirty, git_head
from .schemas import is_denied, load_document

SCHEMA_VERSION = "memory/v2alpha1"
RUNTIME_DIR = ".agent-runtime"
DEFAULT_LIMIT = 20

# ---------------------------------------------------------------------------
# Classification (deterministic heuristics — documented as such)
# ---------------------------------------------------------------------------

_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "security": (
        "security",
        "secret",
        "csrf",
        "xss",
        "privacy",
        "auth",
        "authorization",
        "private",
        "hmac",
        "секрет",
        "приватн",
        "безопасн",
        "утечк",
        "обход",
        "разрешени",
    ),
    "data": (
        "alembic",
        "migration",
        "миграци",
        "schema",
        "table",
        "таблиц",
        "column",
        "поле",
        "ddl",
        "model",
        "модель",
    ),
    "ui": (
        "кнопк",
        "страниц",
        "template",
        "шаблон",
        "html",
        "перевод",
        "i18n",
        "frontend",
        "frontend",
        "ui",
        "фронт",
        "локализ",
        "отображ",
        "рендер",
    ),
    "deploy": ("deploy", "docker", "nginx", "healthz", "readiness", "compose", "депло", "разверн", "задепло"),
    "product": (
        "решение",
        "продукт",
        "контур",
        "приоритет",
        "decision",
        "product",
        "владелец",
        "roadmap",
        "как должен",
    ),
    "fact": (
        "сколько",
        "какая последняя",
        "реализован ли",
        "статус",
        "как работает",
        "почему",
        "найди",
        "найти",
        "find",
        "list",
        "где",
    ),
    "code": (
        "route",
        "endpoint",
        "handler",
        "service",
        "переименов",
        "сигнатур",
        "consumer",
        "call site",
        "реализ",
        "измен",
        "добав",
        "чинит",
        "refactor",
        "split",
        "баг",
        "bug",
        "функци",
        "сервис",
    ),
}

_SCOPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "locktimer/core": (
        "locktimer",
        "timer",
        "slot",
        "chastity",
        "safety stop",
        "safety_stop",
        "safety-stop",
        "tag",
        "бирк",
        "пломб",
        "unlock window",
        "lock session",
        "penalty",
        "слот",
    ),
    "social": (
        "social",
        "relationship",
        "invitation",
        "moderation",
        "grant",
        "block",
        "profile",
        "публикац",
        "feed",
        "верификаци",
        "verification",
    ),
    "llm": (
        "llm",
        "provider",
        "prompt",
        "api_key",
        "raw_llm",
        "generation",
        "abstract",
        "omniroute",
        "groq",
        "openrouter",
        "generat",
        "провайдер",
    ),
    "tracker/core": (
        "entity",
        "activity",
        "task",
        "points",
        "training",
        "diet",
        "inventory",
        "measurement",
        "calendar",
        "gamification",
        "opt-in",
        "catalog",
        "каталог",
        "задач",
    ),
    "platform/time": ("timezone", "tz", "local_day", "local_today", "device", "сутк", "границ", "часовой пояс"),
    "platform/media": ("media", "upload", "attachment", "thumbnail", "image", "photo", "фото", "media"),
    "platform/auth": ("auth", "jwt", "login", "register", "csrf", "session", "access_token"),
    "data/migrations": ("alembic", "migration", "миграци"),
    "tests": ("тест", "test", "pytest", "fixture"),
    "engineering/memory": ("memory", "память", "adr", "wiki", "memoryctl", "bootstrap"),
}

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "are",
    "was",
    "how",
    "what",
    "where",
    "как",
    "что",
    "где",
    "для",
    "это",
    "при",
    "или",
    "все",
    "всех",
    "нужно",
    "надо",
    "есть",
    "find",
    "list",
    "по",
    "на",
    "из",
}


def _normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


def classify_task(text: str) -> dict[str, list[str]]:
    """Deterministic task classification → {classes, scopes}."""
    low = _normalize(text)
    classes = sorted({cls for cls, kws in _CLASS_KEYWORDS.items() if any(k in low for k in kws)})
    scopes = sorted({sc for sc, kws in _SCOPE_KEYWORDS.items() if any(k in low for k in kws)})
    if not classes:
        classes = ["code"]
    if not scopes:
        scopes = ["platform"]
    return {"classes": classes, "scopes": scopes}


def _extract_symbols(text: str) -> set[str]:
    """Identifiers that look like code symbols (snake_case or CamelCase)."""
    out: set[str] = set()
    for m in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", text):
        w = m.group(0)
        if "_" in w or (w[0].isupper() and any(c.islower() for c in w[1:])):
            out.add(w)
    return out


def _extract_terms(text: str) -> set[str]:
    words = re.findall(r"[a-zа-я0-9_]{3,}", _normalize(text))
    return {w for w in words if w not in _STOPWORDS}


# ---------------------------------------------------------------------------
# Canonical docs (L0/L1)
# ---------------------------------------------------------------------------

_L0_GLOBS = ("knowledge.md", "app/**/knowledge.md")


def collect_docs(root: Path, classification: dict, task_text: str, limit: int = 12) -> list[dict]:
    """Select L0 (always) + L1 (scope/keyword-matched) canonical docs."""
    scopes = set(classification["scopes"])
    terms = _extract_terms(task_text)
    symbols = _extract_symbols(task_text)

    sources: list[dict] = []

    # L0 — AGENTS.md (legacy contract) always included.
    agents = root / "AGENTS.md"
    if agents.exists():
        sources.append(
            {
                "id": "AGENTS.md",
                "path": "AGENTS.md",
                "kind": "contract",
                "status": "active",
                "authority": "normative",
                "reason": "always-on (L0)",
            }
        )

    # L0 — knowledge.md (root + domain-local), scope-filtered.
    for glob in _L0_GLOBS:
        for p in sorted(root.glob(glob)):
            rel = p.relative_to(root).as_posix()
            if is_denied(rel):
                continue
            doc = load_document(p)
            meta = doc.meta or {}
            doc_scopes = set(meta.get("scope", []))
            is_root = rel == "knowledge.md"
            if not is_root and meta and doc_scopes and not _scope_overlap(doc_scopes, scopes):
                continue  # domain contract not relevant to this task
            sources.append(
                {
                    "id": meta.get("id") or rel,
                    "path": rel,
                    "kind": meta.get("kind", "contract"),
                    "status": meta.get("status", "active"),
                    "authority": meta.get("authority", "technical"),
                    "reason": "always-on (L0)",
                }
            )

    # L1 — docs/adr, docs/wiki, docs/questions, scored by scope + keyword overlap.
    candidates: list[tuple[int, dict]] = []
    for glob in ("docs/adr/*.md", "docs/wiki/*.md", "docs/questions/*.md"):
        for p in sorted(root.glob(glob)):
            if p.name == "README.md":
                continue
            rel = p.relative_to(root).as_posix()
            if is_denied(rel):
                continue
            doc = load_document(p)
            if not doc.has_frontmatter:
                continue
            meta = doc.meta
            status = meta.get("status")
            # exclude superseded/answered/archived/historical by default
            if status in ("superseded", "answered", "archived", "cancelled"):
                continue
            score = _doc_score(meta, doc.body, scopes, terms, symbols)
            if score > 0:
                candidates.append(
                    (
                        score,
                        {
                            "id": meta.get("id") or rel,
                            "path": rel,
                            "kind": meta.get("kind"),
                            "status": status,
                            "authority": meta.get("authority"),
                            "reason": _doc_reason(meta, doc.body, scopes, terms, symbols),
                        },
                    )
                )
    candidates.sort(key=lambda x: (-x[0], x[1]["path"]))
    sources.extend(entry for _, entry in candidates[:limit])

    # dedupe by path
    seen: set[str] = set()
    unique: list[dict] = []
    for s in sources:
        if s["path"] not in seen:
            seen.add(s["path"])
            unique.append(s)
    return unique


def _scope_overlap(doc_scopes: set[str], task_scopes: set[str]) -> bool:
    if not doc_scopes:
        return True
    for ds in doc_scopes:
        for ts in task_scopes:
            if ds == ts or ds.startswith(ts.split("/")[0]) or ts.startswith(ds.split("/")[0]):
                return True
    return False


def _doc_score(meta: dict, body: str, scopes: set, terms: set, symbols: set) -> int:
    score = 0
    doc_scopes = set(meta.get("scope", []))
    if _scope_overlap(doc_scopes, scopes):
        score += 5
    hay = _normalize((meta.get("title") or "") + "\n" + body)
    for t in terms:
        if t in hay:
            score += 1
    for s in symbols:
        if s in body:
            score += 2
    return score


def _doc_reason(meta: dict, body: str, scopes: set, terms: set, symbols: set) -> str:
    parts: list[str] = []
    if _scope_overlap(set(meta.get("scope", [])), scopes):
        parts.append("scope-match")
    hay = _normalize((meta.get("title") or "") + "\n" + body)
    if any(t in hay for t in terms):
        parts.append("keyword")
    return ", ".join(parts) or "keyword"


# ---------------------------------------------------------------------------
# Code search (exact/lexical, pure-Python)
# ---------------------------------------------------------------------------

_SCAN_DIRS = ("app", "tests", "alembic")
_SCAN_SUFFIXES = {".py", ".html", ".js", ".md", ".yml", ".yaml", ".toml"}


def _iter_scan_files(root: Path):
    for d in _SCAN_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in _SCAN_SUFFIXES:
                continue
            rel = p.relative_to(root).as_posix()
            if is_denied(rel):
                continue
            yield p, rel


def search_code(root: Path, task_text: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Exact/lexical search: symbols first, then terms, across allowlisted files."""
    symbols = _extract_symbols(task_text)
    terms = _extract_terms(task_text)
    scored: list[tuple[int, str, list[str]]] = []

    for p, rel in _iter_scan_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        score = 0
        matched: list[str] = []
        for s in sorted(symbols):
            if s in text:
                score += 3
                matched.append(s)
        low = _normalize(text)
        for t in sorted(terms):
            if t in low:
                score += 1
                matched.append(t)
        if score > 0:
            scored.append((score, rel, matched[:8]))

    scored.sort(key=lambda x: (-x[0], x[1]))
    results: list[dict] = []
    for score, rel, matched in scored[:limit]:
        results.append({"path": rel, "score": score, "matched_by": matched})
    return results


def build_impact_frontier(root: Path, code_results: list[dict], task_text: str) -> dict:
    """Find related tests, migrations and call sites for the top matched symbols."""
    symbols = _extract_symbols(task_text)
    for r in code_results:
        for w in r.get("matched_by", []):
            if "_" in w or (w and w[0].isupper()):
                symbols.add(w)
    if not symbols:
        return {"tests": [], "migrations": [], "call_sites": []}

    tests: list[str] = []
    migrations: list[str] = []
    call_sites: list[str] = []
    matched_paths = {r["path"] for r in code_results}

    for p, rel in _iter_scan_files(root):
        if rel in matched_paths:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not any(s in text for s in symbols):
            continue
        if rel.startswith("tests/"):
            tests.append(rel)
        elif rel.startswith("alembic/"):
            migrations.append(rel)
        elif rel.startswith("app/"):
            call_sites.append(rel)

    return {
        "tests": sorted(set(tests)),
        "migrations": sorted(set(migrations)),
        "call_sites": sorted(set(call_sites)),
    }


# ---------------------------------------------------------------------------
# Risks / required checks
# ---------------------------------------------------------------------------


def required_checks(classification: dict) -> list[str]:
    classes = set(classification["classes"])
    scopes = set(classification["scopes"])
    checks = ["memoryctl facts --check"]
    if classes & {"code", "ui", "data", "security"} or scopes & {"tests", "data/migrations"}:
        checks.append("pytest tests/")
    if "security" in classes:
        checks.append("memoryctl lint")
    if scopes & {"data/migrations"} or "data" in classes:
        checks.append("alembic heads")
    if "code" in classes:
        checks.append("ruff check <changed files>")
    return checks


def risks(classification: dict) -> list[str]:
    scopes = set(classification["scopes"])
    classes = set(classification["classes"])
    out: list[str] = []
    if "locktimer/core" in scopes:
        out += [
            "safety stop always available (PD-006)",
            "penalty not wired to HTTP — EQ-0014",
            "slot open window needs max_late_seconds",
        ]
    if "social" in scopes:
        out += ["redact raw_llm_response/user_id in projections", "moderation gate before public access"]
    if "llm" in scopes:
        out += ["no safety-filter bypass", "raw_llm_response optional (ADR-034)"]
    if "platform/media" in scopes:
        out += ["owner-scoped serving (P0-1)"]
    if "security" in classes or "platform/auth" in scopes:
        out += ["CHALLENGE_HMAC_KEY required in prod (P0-2)", "CSRF on state-changing requests"]
    if "data" in classes or "data/migrations" in scopes:
        out += ["single Alembic head", "no create_all in startup"]
    return out


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def _task_hash(task_text: str) -> str:
    return "sha256:" + hashlib.sha256(task_text.encode("utf-8")).hexdigest()


def _new_session_id() -> str:
    return f"{int(time.time() * 1000)}-{secrets.token_hex(6)}"


def bootstrap(
    root: Path,
    task_text: str,
    *,
    session_id: str | None = None,
    now: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Build a context pack (and sentinel) for the given task."""
    task_text = task_text.strip()
    if not task_text:
        raise ValueError("task text must not be empty")

    head = git_head(root)
    classification = classify_task(task_text)
    docs = collect_docs(root, classification, task_text)
    code = search_code(root, task_text, limit=limit)
    impact = build_impact_frontier(root, code, task_text)

    mode = "blocked" if head is None else "normal"

    sources = docs + [
        {
            "path": r["path"],
            "authority": "factual",
            "status": "current",
            "reason": "lexical: " + ", ".join(r["matched_by"]),
            "retriever": "lexical",
        }
        for r in code
    ]

    pack: dict = {
        "schema_version": SCHEMA_VERSION,
        "kind": "context_pack",
        "session_id": session_id or _new_session_id(),
        "task_hash": _task_hash(task_text),
        "task": task_text,
        "created_at": now or datetime.now(UTC).isoformat(),
        "start_head": head,
        "branch": git_branch(root),
        "dirty": git_dirty(root),
        "mode": mode,
        "classification": classification,
        "sources": sources,
        "symbols": sorted(_extract_symbols(task_text)),
        "impact_frontier": impact,
        "risks": risks(classification),
        "required_checks": required_checks(classification),
        "excluded_paths": [],
        "size_bytes": 0,
        "status": "ready" if mode == "normal" else "blocked",
    }
    pack["size_bytes"] = len(json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True))
    return pack


def write_pack(root: Path, pack: dict, runtime_dir: str = RUNTIME_DIR) -> Path:
    runtime = root / runtime_dir
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / "context-pack.json"
    path.write_text(json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_sentinel(root: Path, pack: dict, runtime_dir: str = RUNTIME_DIR) -> Path:
    runtime = root / runtime_dir
    runtime.mkdir(parents=True, exist_ok=True)
    sentinel = {
        "schema_version": SCHEMA_VERSION,
        "kind": "session_sentinel",
        "session_id": pack["session_id"],
        "task_hash": pack["task_hash"],
        "start_head": pack["start_head"],
        "pack_hash": "sha256:"
        + hashlib.sha256(json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "created_at": pack["created_at"],
        "status": pack["status"],
    }
    path = runtime / "session.json"
    path.write_text(json.dumps(sentinel, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_bootstrap(
    root: Path, task_text: str, *, session_id: str | None = None, runtime_dir: str = RUNTIME_DIR
) -> tuple[dict, Path, Path]:
    """Full pipeline: build pack, write pack + sentinel. Returns (pack, pack_path, sentinel_path)."""
    pack = bootstrap(root, task_text, session_id=session_id)
    pack_path = write_pack(root, pack, runtime_dir=runtime_dir)
    sentinel_path = write_sentinel(root, pack, runtime_dir=runtime_dir)
    return pack, pack_path, sentinel_path
