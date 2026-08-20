"""Stateful Long-Term Vector Memory & Contextual Recall Engine (Step 46 / ADR-123)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.retrieve import retrieve_relevant

logger = logging.getLogger(__name__)


async def recall_user_memories(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieves semantic long-term memories for user query via Qdrant & Lexical fallback."""
    try:
        results = await retrieve_relevant(db=db, user_id=user_id, query=query, limit=limit)
        return results
    except Exception as exc:
        logger.warning("Memory recall failed: %s", exc)
        return []


def format_memory_context(memories: list[dict[str, Any]]) -> str:
    """Formats retrieved memories into a structured system context string."""
    if not memories:
        return "Нет релевантных воспоминаний о прошлых практиках."

    formatted = []
    for idx, mem in enumerate(memories, start=1):
        source = mem.get("source", "kb")
        text = mem.get("text", "")
        formatted.append(f"{idx}. [{source}] {text}")

    return "\n".join(formatted)
