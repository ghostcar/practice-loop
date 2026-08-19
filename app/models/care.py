"""Personal Care (M3 Personal Suite, ROADMAP §7 4B).

Уход, косметика, гигиена, процедуры и внешность (PRODUCT_OVERVIEW §8) —
**relief-only** (PD-013): никакой игровой интеграции (XP/баллы/штрафы).
Все записи — Private Record (DATA_LIFECYCLE.md): отдельное удаление,
связи с Health/Timer — по ID без раскрытия (мягкие ссылки без FK).

Таблицы:
- ``care_routines`` — каталог процедур/рутин (лицо/тело/волосы/руки/ноги,
  бритьё и депиляция, массаж, маникюр/педикюр, стрижки/окрашивание, домашние
  и салонные), частота, заметки;
- ``care_entries``  — факты выполнения процедуры: дата, длительность,
  реакция кожи, заметки, снимок расчётной фазы Cycle и мягкая связь с
  медиа (фото динамики) через owner_type=care_entry;
- ``care_products`` — каталог средств/косметики (очищение/сыворотки/уход),
  с привязкой к инвентарю (inventory_item_id);
- ``care_entry_products`` — какие средства использованы в записи ухода
  (many-to-many care_entries ↔ care_products).

Расчётная фаза Cycle никогда не выдаётся за факт (§9.4).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.catalog import ActivityCatalogItem
    from app.models.life import InventoryItem
    from app.models.user import User

# зоны ухода
CARE_AREAS = ("face", "body", "hair", "hands", "feet", "other")
# тип процедуры: домашняя / салонная
CARE_KINDS = ("home", "salon")
# реакция кожи — 1..5 (лучше/хуже)
SCALE_1_5 = (1, 2, 3, 4, 5)
# категории средств/косметики
CARE_PRODUCT_CATEGORIES = (
    "cleanser",
    "toner",
    "serum",
    "moisturizer",
    "mask",
    "exfoliant",
    "sun",
    "body",
    "hair",
    "other",
)


class CareRoutine(Base):
    """Каталог процедур/рутин ухода (PRODUCT_OVERVIEW §8)."""

    __tablename__ = "care_routines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # ссылка на универсальный каталог (ADR-091) — вид процедуры ухода
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_catalog.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # face | body | hair | hands | feet | other
    area: Mapped[str] = mapped_column(String(20), default="other", nullable=False)
    # home | salon
    kind: Mapped[str] = mapped_column(String(20), default="home", nullable=False)
    # место проведения (салон и т.п., может быть адрес) — необязательно (2026-08-19)
    place_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    place_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # частота в днях (например 7 = раз в неделю) — необязательно
    frequency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    # рекомендуемые средства для этой процедуры (care_routine_products)
    products: Mapped[list[CareProduct]] = relationship(
        "CareProduct", secondary="care_routine_products", lazy="selectin", viewonly=True
    )

    def __repr__(self) -> str:
        return f"<CareRoutine(id={self.id}, name={self.name!r})>"


class CareEntry(Base):
    """Факт выполнения процедуры ухода (PRODUCT_OVERVIEW §8).

    Мягкая связь с медиа (фото динамики) — через owner_type=care_entry в
    media registry; связь с Cycle — снимок расчётной фазы на дату процедуры.
    """

    __tablename__ = "care_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    routine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("care_routines.id", ondelete="SET NULL"), nullable=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # реакция кожи — 1..5 (1 = хуже, 5 = лучше)
    skin_reaction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # место проведения процедуры (салон и т.п.) — необязательно (2026-08-19)
    place_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    place_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # снимок расчётной фазы Cycle (не выдаётся за факт, §9.4)
    cycle_phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cycle_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    routine: Mapped[CareRoutine | None] = relationship("CareRoutine", lazy="selectin")
    products: Mapped[list[CareProduct]] = relationship(
        "CareProduct", secondary="care_entry_products", lazy="selectin", viewonly=True
    )

    def __repr__(self) -> str:
        return f"<CareEntry(id={self.id}, date={self.entry_date})>"


class CareProduct(Base):
    """Каталог средств/косметики для ухода (PRODUCT_OVERVIEW §8).

    Каждая позиция может ссылаться на предмет инвентаря (inventory_item_id) —
    чтобы вести остатки/список покупок в одном месте, и на универсальный каталог
    (catalog_item_id, домен care). У позиции есть остаток (quantity) и срок
    (expiry_date). Категории — из CARE_PRODUCT_CATEGORIES. Средства используются
    в записях ухода (care_entry_products) и рекомендуются для процедур
    (care_routine_products). Relief-only (PD-013): справочник без игровой
    интеграции.
    """

    __tablename__ = "care_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # cleanser | toner | serum | moisturizer | mask | exfoliant | sun | body | hair | other
    category: Mapped[str] = mapped_column(String(30), default="other", nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # остаток (штук/мл — условно), 0/None = неизвестно
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # срок годности (необязательно)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # привязка к инвентарю: остаток/список покупок ведётся в inventory_items
    inventory_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # ссылка на универсальный каталог (ADR-091, домен care) — вид активности
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_catalog.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    inventory_item: Mapped[InventoryItem | None] = relationship("InventoryItem", lazy="selectin")
    catalog_item: Mapped[ActivityCatalogItem | None] = relationship("ActivityCatalogItem", lazy="selectin")

    def __repr__(self) -> str:
        return f"<CareProduct(id={self.id}, name={self.name!r})>"


class CareRoutineProduct(Base):
    """Many-to-many: рекомендуемые средства для процедуры ухода."""

    __tablename__ = "care_routine_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    routine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("care_routines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("care_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<CareRoutineProduct(routine={self.routine_id}, product={self.product_id})>"


class CareCourse(Base):
    """Курс процедур (серия сеансов) — лазер, массаж, пилинг (Шаг 17c, ADR-095).

    Курс объединяет N сеансов с интервалом между ними; прогресс и следующая
    дата сеанса считаются по ``care_course_sessions``. Relief-only (PD-013).
    """

    __tablename__ = "care_courses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # ссылка на универсальный каталог (ADR-091) — вид процедуры курса
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_catalog.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # face | body | hair | hands | feet | other
    area: Mapped[str] = mapped_column(String(20), default="other", nullable=False)
    # место проведения курса (салон и т.п.) — необязательно (2026-08-19)
    place_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    place_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    total_sessions: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # интервал между сеансами в днях (напр. 30 для лазера)
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # active | completed | archived
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    sessions: Mapped[list[CareCourseSession]] = relationship(
        "CareCourseSession", back_populates="course", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<CareCourse(id={self.id}, name={self.name!r})>"


class CareCourseSession(Base):
    """Сеанс курса процедур: номер, запланированная дата, статус, связь с записью ухода."""

    __tablename__ = "care_course_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("care_courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # pending | done | skipped
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # мягкая ссылка на запись ухода (факт выполнения процедуры)
    entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("care_entries.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    course: Mapped[CareCourse] = relationship("CareCourse", back_populates="sessions")
    entry: Mapped[CareEntry | None] = relationship("CareEntry", lazy="selectin")

    def __repr__(self) -> str:
        return f"<CareCourseSession(course={self.course_id}, #{self.session_number}, {self.status})>"


class CareEntryProduct(Base):
    """Many-to-many: какие средства использованы в записи ухода."""

    __tablename__ = "care_entry_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("care_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("care_products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<CareEntryProduct(entry={self.entry_id}, product={self.product_id})>"
