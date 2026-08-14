"""Private knowledge base API (ADR-070, Step 6) — служебный доступ.

База знаний не является пользовательским UI-модулем (решение владельца):
это служебный слой для обогащения промптов. Здесь — минимальный read-only
JSON API (для диагностики и будущего использования ботами/mobile):

- GET /api/v2/knowledge/status  → {available, reason?}
- GET /api/v2/knowledge/search?q=... → {query, results, available}
- POST /api/v2/knowledge/reindex → {status, docs} (пересобрать индекс)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.knowledge.index import kb_backend_available
from app.knowledge.service import search_knowledge
from app.models.user import User

router = APIRouter(prefix="/api/v2/knowledge", tags=["knowledge"])


@router.get("/status")
async def knowledge_status(
    user: User = Depends(get_current_user),
):
    """Векторный backend KB готов или нет (и почему)."""
    available, reason = kb_backend_available()
    return {"available": available, "reason": reason if not available else None}


@router.get("/search")
async def knowledge_search(
    q: str = Query(..., min_length=1, max_length=300),
    limit: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Поиск по собственной базе знаний (только свои данные)."""
    return await search_knowledge(db, user.id, q, limit=limit)


@router.post("/reindex")
async def knowledge_reindex(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Пересобрать индекс KB из текущих данных пользователя (идемпотентно)."""
    from app.knowledge.index import index_user_documents

    result = await index_user_documents(db, user.id)
    if result["status"] == "blocked":
        raise HTTPException(status_code=503, detail=result.get("reason", "KB backend unavailable"))
    return result
