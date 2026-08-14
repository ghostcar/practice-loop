"""KB document collection + vector indexing (Qdrant + Omniroute).

Собирает документы из существующих данных пользователя и индексирует их в
Qdrant (коллекция ``personal_kb``). Точки идентифицируются content-хэшем
(детерминированный UUID из sha256), поэтому повторная индексация идемпотентна.

Всё опционально: без ``memory`` deps или OMNIROUTE_* — функции возвращают
пустой результат/статус, не бросая исключений в прикладной путь.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

COLLECTION = "personal_kb"
INDEX_DIRNAME = ".memory-local/personal-kb"
PROFILE_HASH = "omniroute:text-embedding-3-small:1536"

# ── Helpers (переиспользуют подход tools/memoryctl/vectors.py) ──────────────


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def point_id(content_hash: str) -> str:
    return str(uuid.UUID(content_hash.split(":", 1)[-1][:32]))


def omniroute_settings() -> dict:
    """Read OMNIROUTE_HOST / OMNIROUTE_API_KEY from env, then .env (stdlib-only)."""
    out: dict = {}
    env_file = Path(".env")
    file_vars: dict = {}
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            file_vars[k.strip()] = v.strip().strip('"').strip("'")
    for key in ("OMNIROUTE_HOST", "OMNIROUTE_API_KEY"):
        out[key] = os.environ.get(key) or file_vars.get(key, "")
    return out


def kb_backend_available() -> tuple[bool, str]:
    """Whether the vector backend (qdrant + Omniroute config) is present."""
    try:
        import qdrant_client  # noqa: F401
    except ImportError as exc:  # pragma: no cover - env dependent
        return False, f"optional 'memory' deps not installed ({exc.name})"
    omni = omniroute_settings()
    if not omni["OMNIROUTE_HOST"] or not omni["OMNIROUTE_API_KEY"]:
        return False, "OMNIROUTE_HOST / OMNIROUTE_API_KEY not configured"
    return True, "ok"


class Embedder:
    """Dense embeddings via Omniroute /v1/embeddings (OpenAI-compatible)."""

    MODEL = "openrouter/openai/text-embedding-3-small"

    def __init__(self, host: str, api_key: str) -> None:
        import httpx

        base = host.rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = "https://" + base
        self._client = httpx.Client(timeout=120.0)
        self._url = f"{base}/v1/embeddings"
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.post(self._url, headers=self._headers, json={"model": self.MODEL, "input": texts})
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [[float(x) for x in d["embedding"]] for d in data]


class QdrantStore:
    """Local/persistent Qdrant store (no server, no port)."""

    def __init__(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        index_dir = Path(INDEX_DIRNAME)
        index_dir.mkdir(parents=True, exist_ok=True)
        self._client = QdrantClient(path=str(index_dir))
        self._Distance = Distance
        self._VectorParams = VectorParams

    def _ensure_collection(self, dim: int) -> None:
        if not self._client.collection_exists(COLLECTION):
            self._client.create_collection(
                collection_name=COLLECTION,
                vectors_config=self._VectorParams(size=dim, distance=self._Distance.COSINE),
            )

    def upsert(self, docs: list[dict], vectors: list[list[float]]) -> int:
        from qdrant_client.models import PointStruct

        if not docs or not vectors:
            return 0
        self._ensure_collection(len(vectors[0]))
        points = [
            PointStruct(id=point_id(d["content_hash"]), vector=v, payload={k: d[k] for k in d if k != "content_hash"})
            for d, v in zip(docs, vectors, strict=True)
        ]
        self._client.upsert(collection_name=COLLECTION, points=points, wait=True)
        return len(points)

    def search(self, vector: list[float], user_id: str, limit: int) -> list[dict]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        if not self._client.collection_exists(COLLECTION):
            return []
        res = self._client.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=limit,
            with_payload=True,
            query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]),
        )
        out: list[dict] = []
        for hit in res.points:
            payload = dict(hit.payload or {})
            text = payload.get("text", "")
            source = payload.get("source", "")
            out.append({"text": text, "source": source, "score": float(hit.score)})
        return out


# ── Document collection ──────────────────────────────────────────────────────


def _doc(text: str, source: str, user_id: str) -> dict:
    content_hash = "sha256:" + _sha256_hex(text)
    return {
        "content_hash": content_hash,
        "user_id": str(user_id),
        "text": text,
        "source": source,
    }


async def collect_user_documents(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Собрать документы из существующих данных пользователя (служебно)."""
    docs: list[dict] = []
    user_id_str = str(user_id)

    # 1. История активностей — названия, параметры, комментарии
    from app.models.activity_log import ActivityLog

    logs_result = await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user_id).order_by(ActivityLog.created_at.desc()).limit(200)
    )
    for log in logs_result.scalars().all():
        parts = [log.selected_entity_name or "activity"]
        if log.selected_params:
            parts.append(f"params: {json.dumps(log.selected_params, ensure_ascii=False)}")
        if log.actual_parameters:
            parts.append(f"actual: {json.dumps(log.actual_parameters, ensure_ascii=False)}")
        if log.planned_comment:
            parts.append(f"note: {log.planned_comment}")
        docs.append(_doc(" | ".join(parts), f"activity_log:{log.id}", user_id_str))

    # 2. Диеты — название, описание, направление, цель
    from app.models.diet import Diet

    diet_result = await db.execute(select(Diet).where(Diet.user_id == user_id).limit(50))
    for d in diet_result.scalars().all():
        parts = [f"diet: {d.name or ''}", f"direction: {d.direction or ''}", f"goal: {d.goal or ''}"]
        if getattr(d, "description", None):
            parts.append(str(d.description))
        docs.append(_doc(" | ".join(p for p in parts if p), f"diet:{d.id}", user_id_str))

    # 3. Тренировочные дни — цели и суммари
    from app.models.training import TrainingDay

    training_result = await db.execute(
        select(TrainingDay).where(TrainingDay.user_id == user_id).order_by(TrainingDay.target_date.desc()).limit(50)
    )
    for td in training_result.scalars().all():
        parts = [f"training day: {td.target_date.isoformat() if td.target_date else ''}"]
        if getattr(td, "plan_summary", None):
            parts.append(f"plan: {td.plan_summary}")
        docs.append(_doc(" | ".join(p for p in parts if p), f"training_day:{td.id}", user_id_str))

    return docs


async def index_user_documents(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Собрать и проиндексировать документы пользователя. Идемпотентно.

    Returns {"status": "ok"|"blocked", "docs": N, "reason": str?}.
    """
    available, reason = kb_backend_available()
    if not available:
        return {"status": "blocked", "docs": 0, "reason": reason}

    docs = await collect_user_documents(db, user_id)
    if not docs:
        return {"status": "ok", "docs": 0}

    omni = omniroute_settings()
    embedder = Embedder(omni["OMNIROUTE_HOST"], omni["OMNIROUTE_API_KEY"])
    store = QdrantStore()

    # Chunked embed→upsert (remote API, bounded request sizes).
    batch = 32
    total = 0
    for i in range(0, len(docs), batch):
        chunk = docs[i : i + batch]
        vectors = embedder.embed([d["text"] for d in chunk])
        total += store.upsert(chunk, vectors)
    return {"status": "ok", "docs": total}
