"""Consent records (C3, PRODUCT_OVERVIEW — согласия и чек-ины).

Журнал явных согласий на чувствительную обработку: расширенный LLM-режим
(детальный разбор анализов/рекомендации), отправка фото на LLM-верификацию,
обработка персональных данных. Согласие — запись с явным `granted`/`revoked`
состоянием и историей переходов (не перезаписывается: каждое изменение —
новая версия). **Relief-only** (PD-013): без игровой интеграции.

Записи — Private Record (DATA_LIFECYCLE.md): принадлежат только владельцу.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

# известные типы согласий
CONSENT_TYPES = ("llm_expanded", "media_verification", "data_processing", "custom")
CONSENT_STATES = ("granted", "revoked")


class ConsentRecord(Base):
    """Запись согласия на чувствительную обработку (granted/revoked)."""

    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # llm_expanded | media_verification | data_processing | custom
    consent_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # granted | revoked
    state: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # описание объёма согласия (свободный текст)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    # версия согласия (каждое изменение создаёт новую запись)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConsentRecord(id={self.id}, type={self.consent_type}, state={self.state})>"
