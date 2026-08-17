"""Universal Activity Catalog (сквозной каталог активностей).

Единый каталог «видов активностей» по образцу Entity (категории/теги/описание),
на который могут ссылаться любые модули личного контура:

- ``sj_entries.catalog_item_id``     — вид активности в Sexual Journal;
- ``care_routines.catalog_item_id``  — вид процедуры ухода;
- ``lock_slot_rules.catalog_item_id``— причина/цель окна таймера;
- ``entities.catalog_item_id``       — трекер-задача ссылается на универсальный вид.

Каталог нейтрален по своей природе (relief-only, PD-013): это справочник, без
игровой интеграции (XP/баллы/штрафы). Системные записи (``owner_id = NULL``)
видны всем; пользовательские — только владельцу. Поле ``domains`` (JSON-список
контекстов: journal/care/timer/tracker) позволяет фильтровать пикеры; пустой
список или NULL = запись применима везде («сквозная»).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.category import ActivityCategory
    from app.models.user import User

# контексты применения записи каталога; пусто/None = применима везде
CATALOG_DOMAINS = ("journal", "care", "timer", "tracker")


class ActivityCatalogItem(Base):
    """Универсальная запись каталога активностей (сквозная, как Entity)."""

    __tablename__ = "activity_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # контексты применения: ["journal","care","timer","tracker"]; пусто/None = везде
    domains: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # NULL = системная запись (видна всем); иначе — пользовательская (только владельцу)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    category_rel: Mapped[ActivityCategory | None] = relationship("ActivityCategory", lazy="selectin")
    owner: Mapped[User | None] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ActivityCatalogItem(id={self.id}, name={self.name!r})>"
