"""memoryctl vectors — M3 vector pilot (ADR-069): Qdrant local + BGE-M3 (shadow).

Optional-dependency backend. Imports of ``qdrant_client`` and ``fastembed`` are
lazy and guarded by :func:`is_available`; every command degrades to a clear
message (or to the exact/lexical fallback) when the optional ``memory`` dev-group
is not installed. The index lives in ``.memory-local/code-index/`` (gitignored)
and is fully reproducible from the current Git HEAD — it is never committed.

Retrieval contract (CODE_MEMORY_DESIGN.md §8, ADR-069): dense ANN (BGE-M3,
multilingual RU→EN) fused with the deterministic lexical searcher from
``bootstrap.search_code`` via client-side reciprocal-rank fusion (RRF), then
exact-confirmed against the worktree. Vector similarity never raises authority:
the exact/lexical floor is always preserved, and every result carries a
``confirmation`` verdict.

Commands (via __main__.py):
    python -m tools.memoryctl index-code [--mode full|incremental|check|shadow|rebuild]
    python -m tools.memoryctl search-code --query "..."
"""

from __future__ import annotations

import json
import math
import re
import uuid
from pathlib import Path

from . import bootstrap, code_units
from .facts import git_branch, git_dirty, git_head
from .schemas import is_denied

SCHEMA_VERSION = "memory/v2alpha1"
PARSER_VERSION = code_units.PARSER_VERSION
INDEX_RELPATH = ".memory-local/code-index"
MANIFEST_NAME = "manifest.json"
COLLECTION = "code_units"

# Embedding profile (ADR-069, CODE_MEMORY_DESIGN.md §6). A second named vector
# (code-specific) is added only if BGE-M3 proves weak on code — see ADR-069.
EMBEDDING_PROFILE = {
    "provider": "local",
    "model": "BGE-M3",
    "model_id": "BAAI/bge-m3",
    "dimensions": 1024,
    "normalization": True,
    "pooling": "mean",
    "max_length": 8192,
    "tokenizer": "xlm-roberta",
    "languages": ["ru", "en", "python", "jinja2", "javascript"],
    "quantization": "int8",
    # BGE-M3 emits dense+sparse in one model; local-mode server fusion is
    # unstable (ADR-069), so the lexical/sparse side is a deterministic
    # client-side BM25/lexical searcher fused with RRF on the client.
    "sparse": "client-lexical-fallback",
}


def profile_hash(profile: dict | None = None) -> str:
    raw = json.dumps(profile or EMBEDDING_PROFILE, sort_keys=True, ensure_ascii=False)
    return "sha256:" + _sha256_hex(raw)


def _sha256_hex(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def point_id(content_hash: str) -> str:
    """Content-addressed point ID (RFC §5): deterministic UUID from sha256."""
    hexdigest = content_hash.split(":", 1)[-1]
    return str(uuid.UUID(hexdigest[:32]))


def is_available() -> tuple[bool, str]:
    """Whether the optional vector dependencies are importable."""
    try:
        import fastembed  # noqa: F401
        import qdrant_client  # noqa: F401
    except ImportError as exc:  # pragma: no cover - env dependent
        return False, f"optional 'memory' deps not installed ({exc.name}); pip install -e '.[memory]'"
    return True, "ok"


# ---------------------------------------------------------------------------
# Embedder (fastembed, lazy)
# ---------------------------------------------------------------------------


class Embedder:
    """Dense embedding via fastembed (BGE-M3), constructed lazily."""

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name="BGE-M3")

    @property
    def dimensions(self) -> int:
        return int(EMBEDDING_PROFILE["dimensions"])

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.embed(texts)
        return [[float(x) for x in vec] for vec in vectors]


def embed_text(unit: code_units.CodeUnit) -> str:
    """Normalized retrieval text (CODE_MEMORY_DESIGN.md §4)."""
    return f"{unit.scope} | {unit.path} | {unit.unit_kind} | {unit.symbol}\n{unit.signature}\n{unit.retrieval_text}"


# ---------------------------------------------------------------------------
# Qdrant store (lazy)
# ---------------------------------------------------------------------------


class QdrantStore:
    """Local/persistent Qdrant store (dev-only, no server, no port)."""

    def __init__(self, root: Path) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self._root = root
        self._dir = root / INDEX_RELPATH
        self._dir.mkdir(parents=True, exist_ok=True)
        self._client = QdrantClient(path=str(self._dir))
        self._Distance = Distance
        self._VectorParams = VectorParams

    def _ensure_collection(self, dim: int) -> None:
        from qdrant_client.models import PointStruct

        self._PointStruct = PointStruct
        if not self._client.collection_exists(COLLECTION):
            self._client.create_collection(
                collection_name=COLLECTION,
                vectors_config=self._VectorParams(size=dim, distance=self._Distance.COSINE),
            )

    def upsert(self, units: list[code_units.CodeUnit], vectors: list[list[float]]) -> int:
        self._ensure_collection(len(vectors[0]) if vectors else EMBEDDING_PROFILE["dimensions"])
        points = [
            self._PointStruct(
                id=point_id(u.content_hash),
                vector=v,
                payload=u.to_payload(),
            )
            for u, v in zip(units, vectors, strict=True)
        ]
        if points:
            self._client.upsert(collection_name=COLLECTION, points=points, wait=True)
        return len(points)

    def search(self, vector: list[float], limit: int) -> list[dict]:
        if not self._client.collection_exists(COLLECTION):
            return []
        res = self._client.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        out: list[dict] = []
        for hit in res.points:
            payload = dict(hit.payload or {})
            out.append({"path": payload.get("path", ""), "payload": payload, "score": float(hit.score)})
        return out


# ---------------------------------------------------------------------------
# Client-side fusion (RRF) — pure, testable without deps
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(*rankings: list[str], k: int = 60) -> list[tuple[str, float]]:
    """Deterministic RRF over multiple ranked path lists → (path, fused_score)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, path in enumerate(ranking, start=1):
            if path in seen:
                continue
            seen.add(path)
            scores[path] = scores.get(path, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


def lexical_ranking(root: Path, query: str, limit: int) -> list[str]:
    """Deterministic lexical rank (symbol/term) — the exact floor that never regresses."""
    return [r["path"] for r in bootstrap.search_code(root, query, limit=limit)]


def confirm(root: Path, path: str, content_hash: str) -> bool:
    """Exact source confirmation: the unit still exists with the same content hash."""
    p = root / path
    if not p.is_file():
        return False
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(u.content_hash == content_hash for u in code_units.extract_file(path, text))


# ---------------------------------------------------------------------------
# Index / search orchestration
# ---------------------------------------------------------------------------


def manifest_path(root: Path) -> Path:
    return root / INDEX_RELPATH / MANIFEST_NAME


def load_manifest(root: Path) -> dict | None:
    p = manifest_path(root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def index_code(root: Path, *, mode: str = "full", limit: int | None = None) -> dict:
    """Extract units → embed → upsert → write HEAD-bound manifest (RFC §7)."""
    available, reason = is_available()
    if not available:
        return {"available": False, "reason": reason, "status": "blocked"}

    head = git_head(root)
    if head is None:
        return {"available": True, "status": "blocked", "reason": "no Git HEAD (worktree not resolved)"}

    if mode == "check":
        m = load_manifest(root)
        if m is None:
            return {"available": True, "status": "stale", "reason": "no manifest — run index-code"}
        fresh = m.get("head") == head and m.get("profile_hash") == profile_hash()
        return {
            "available": True,
            "status": "ready" if fresh else "stale",
            "head": m.get("head"),
            "unit_count": m.get("unit_count", 0),
        }

    units = code_units.extract_units(root, denylist=is_denied)
    if limit is not None:
        units = units[:limit]

    embedder = Embedder()
    texts = [embed_text(u) for u in units]
    vectors = embedder.embed(texts) if texts else []

    store = QdrantStore(root)
    store.upsert(units, vectors)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "code_index_manifest",
        "head": head,
        "branch": git_branch(root),
        "dirty": git_dirty(root),
        "parser_version": PARSER_VERSION,
        "profile_hash": profile_hash(),
        "profile": EMBEDDING_PROFILE,
        "collection": COLLECTION,
        "unit_count": len(units),
        "mode": mode,
        "status": "ready",
    }
    manifest_path(root).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"available": True, "status": "ready", "head": head, "unit_count": len(units), "mode": mode}


def search_code(root: Path, query: str, *, limit: int = 20, dense_limit: int = 60) -> dict:
    """Hybrid dense+lexical → RRF fusion → exact confirmation (RFC §8)."""
    available, reason = is_available()
    if not available:
        return {"available": False, "reason": reason, "results": []}

    head = git_head(root)
    m = load_manifest(root)
    if m is None or m.get("head") != head or m.get("profile_hash") != profile_hash():
        return {
            "available": True,
            "results": [],
            "stale": True,
            "reason": "index missing or stale for current HEAD — run 'memoryctl index-code'",
        }

    embedder = Embedder()
    qvec = embedder.embed([query])[0]

    store = QdrantStore(root)
    dense = store.search(qvec, limit=dense_limit)

    lex = lexical_ranking(root, query, limit=limit)
    dense_paths = [d["path"] for d in dense]

    fused = reciprocal_rank_fusion(dense_paths, lex)
    dense_score = {d["path"]: d["score"] for d in dense}

    results: list[dict] = []
    for path, score in fused[:limit]:
        payload = next((d["payload"] for d in dense if d["path"] == path), {})
        ch = payload.get("content_hash", "")
        verdict = confirm(root, path, ch) if ch else False
        results.append(
            {
                "path": path,
                "symbol": payload.get("symbol", ""),
                "unit_kind": payload.get("unit_kind", ""),
                "scope": payload.get("scope", ""),
                "fused_score": round(score, 6),
                "dense_score": round(dense_score.get(path, 0.0), 6),
                "matched_by": ["dense", "lexical"]
                if path in dense_paths and path in lex
                else (["dense"] if path in dense_paths else ["lexical"]),
                "confirmation": "exact-read" if verdict else "unconfirmed",
            }
        )
    return {"available": True, "results": results, "stale": False, "head": head}


def ranked_paths(result: dict) -> list[str]:
    """Convenience: the ranked path list from a search_code result (for A/B scoring)."""
    return [r["path"] for r in result.get("results", [])]


def render_index_result(info: dict) -> str:
    if not info.get("available"):
        return f"vectors unavailable: {info.get('reason')}"
    return (
        f"status={info.get('status')} head={info.get('head')} "
        f"units={info.get('unit_count', 0)} mode={info.get('mode', '')}"
    )


_TERM_RE = re.compile(r"[a-zа-я0-9_]{2,}")


def terms(query: str) -> list[str]:
    """Normalized query terms (reused by tests/BM25 probes)."""
    return [t for t in _TERM_RE.findall(query.lower().replace("ё", "е")) if t not in bootstrap._STOPWORDS]


def bm25_like_score(text: str, query_terms: list[str]) -> float:
    """Small deterministic lexical scorer (overlap) — used by the confirm probe."""
    low = text.lower().replace("ё", "е")
    return float(sum(1 for t in query_terms if t in low)) / max(1, len(query_terms))


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity helper for deterministic unit tests."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
