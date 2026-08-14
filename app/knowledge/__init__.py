"""Private knowledge base (ADR-070, Step 6) — служебная система.

База знаний НЕ доступна пользователю напрямую (решение владельца): это
служебный слой, который автоматически индексирует существующие данные
пользователя (история активностей, диеты, планы тренировок, заметки к
задачам) в векторный индекс (Qdrant local + Omniroute embeddings) и
подмешивает релевантные фрагменты в контекст LLM-генерации.

Компоненты:
- ``index.py`` — сборка документов из БД + индексация (Qdrant, коллекция
  ``personal_kb``, user_id в payload);
- ``retrieve.py`` — поиск релевантных фрагментов по запросу (dense + lexical
  fallback);
- ``service.py`` — интеграция с context builder.

Инфраструктура: опциональные deps ``memory`` (qdrant-client). Если они не
установлены или OMNIROUTE_* не настроен — KB деградирует в пустой результат
(без падения генерации).
"""

from app.knowledge.service import (  # noqa: F401
    kb_available,
    retrieve_relevant,
    search_knowledge,
)
