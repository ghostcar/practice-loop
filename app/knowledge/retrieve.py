"""KB retrieval: dense (Qdrant) + deterministic lexical fallback.

Доступен только владельцу данных (фильтр по user_id в payload Qdrant).
Без backend'а возвращает пустой список — генерация не падает.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.index import (
    Embedder,
    QdrantStore,
    kb_backend_available,
    omniroute_settings,
)

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 5


def _lexical_ranking(texts: list[tuple[str, str]], query: str) -> list[tuple[str, str, float]]:
    """Deterministic term-overlap ranking as the fallback floor."""
    terms = [t for t in query.lower().replace("ё", "е").split() if len(t) >= 2]
    if not terms:
        return []
    scored: list[tuple[str, str, float]] = []
    for text, source in texts:
        low = text.lower().replace("ё", "е")
        hits = sum(1 for t in terms if t in low)
        if hits:
            scored.append((text, source, hits / len(terms)))
    scored.sort(key=lambda x: (-x[2], x[1]))
    return scored


async def retrieve_relevant(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Найти релевантные фрагменты KB для запроса. Возвращает [{text, source, score}].

    Lexical fallback работает всегда (собственные документы из БД), даже без
    векторного backend'а — KB никогда не ломает генерацию.
    """
    if not query.strip():
        return []

    # Lexical floor (deterministic, no external deps).
    from app.knowledge.index import collect_user_documents

    docs = await collect_user_documents(db, user_id)
    lexical = _lexical_ranking([(d["text"], d["source"]) for d in docs], query)

    available, _reason = kb_backend_available()
    if not available:
        return [{"text": t, "source": s, "score": round(sc, 3)} for t, s, sc in lexical[:limit]]

    try:
        omni = omniroute_settings()
        embedder = Embedder(omni["OMNIROUTE_HOST"], omni["OMNIROUTE_API_KEY"])
        store = QdrantStore()
        qvec = embedder.embed([query])[0]
        dense = store.search(qvec, str(user_id), limit=limit)
    except Exception as e:  # pragma: no cover - backend errors degrade to lexical
        logger.warning(f"KB dense search failed, using lexical only: {e}")
        dense = []

    if not dense:
        return [{"text": t, "source": s, "score": round(sc, 3)} for t, s, sc in lexical[:limit]]

    # Merge: dense first, fill remaining slots with lexical (RRF-lite).
    seen_sources: set[str] = set()
    merged: list[dict] = []
    for hit in dense:
        if hit["source"] in seen_sources:
            continue
        seen_sources.add(hit["source"])
        merged.append({"text": hit["text"], "source": hit["source"], "score": round(hit["score"], 3)})
        if len(merged) >= limit:
            break
    for text, source, sc in lexical:
        if len(merged) >= limit:
            break
        if source in seen_sources:
            continue
        seen_sources.add(source)
        merged.append({"text": text, "source": source, "score": round(sc, 3)})
    return merged
