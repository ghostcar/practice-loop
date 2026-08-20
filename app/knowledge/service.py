"""KB service facade — точки входа для контекст-билдера и API.

- ``kb_available()`` — bool: векторный backend готов;
- ``retrieve_relevant(db, user_id, query, limit)`` — список фрагментов;
- ``search_knowledge(db, user_id, query, limit)`` — для JSON API;
- ``build_kb_context(db, user_id, query, limit)`` — готовая секция для промпта
  (текст или None, если ничего не найдено/backend недоступен).
"""

from __future__ import annotations

import logging
import os
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

KB_CONTEXT_HEADER = "## Private Knowledge Base (your data, retrieved)"
KB_MAX_FRAGMENT_CHARS = 500


def kb_available() -> bool:
    if os.getenv("KB_CONTEXT_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    from app.knowledge.index import kb_backend_available

    ok, _ = kb_backend_available()
    return ok


async def retrieve_relevant(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    limit: int = 5,
) -> list[dict]:
    """Retrieve relevant private knowledge fragments for a query (dense+lexical)."""
    from app.knowledge.retrieve import retrieve_relevant as _retrieve

    return await _retrieve(db, user_id, query, limit=limit)


async def search_knowledge(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    limit: int = 5,
) -> dict:
    """JSON-API entry: {query, results: [{text, source, score}], available: bool}."""
    if not kb_available():
        return {"query": query, "results": [], "available": False}
    results = await retrieve_relevant(db, user_id, query, limit=limit)
    return {"query": query, "results": results, "available": True}


def format_kb_context(fragments: list[dict], max_chars: int = KB_MAX_FRAGMENT_CHARS) -> str | None:
    """Формат фрагментов для вставки в промпт (безопасно, без утечки чужих данных)."""
    if not fragments:
        return None
    lines = [KB_CONTEXT_HEADER]
    for i, f in enumerate(fragments, start=1):
        text = (f.get("text") or "").strip()
        if not text:
            continue
        if len(text) > max_chars:
            text = text[:max_chars] + "…"
        lines.append(f"{i}. [{f.get('source', 'kb')}] {text}")
    lines.append("Use this context when it is relevant — never invent details from it.")
    if len(lines) == 1:
        return None
    return "\n".join(lines)


async def build_kb_context(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    limit: int = 5,
) -> str | None:
    """Полная секция KB для промпта (None если пусто/недоступно)."""
    if not kb_available() or not query.strip():
        return None
    try:
        fragments = await retrieve_relevant(db, user_id, query, limit=limit)
    except Exception as e:  # pragma: no cover - KB must never break generation
        logger.warning(f"KB retrieval failed, skipping: {e}")
        return None
    return format_kb_context(fragments)
