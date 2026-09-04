"""Medication Organizer (M3 Personal Suite, ROADMAP §7 4C).

Health-модуль — **relief-only** (PD-013): никакой игровой интеграции
(XP/баллы/штрафы не применяются). Все записи — Private Record (DATA_LIFECYCLE.md).

Таблицы:
- ``medications``   — каталог лекарств / БАД / расходников;
- ``med_kits``      — аптечки / места хранения;
- ``med_stocks``    — партия конкретного препарата: количество + срок годности;
- ``med_schedules`` — курс/расписание приёма (доза + частота);
- ``med_intakes``   — факт приёма (taken/missed/skipped/rescheduled/unknown).

``quantity``/``dose`` — Float: таблетки (целые) и жидкие формы (дробные) в одном поле.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.task_location import TaskLocation
    from app.models.user import User

# kind: лекарство / БАД / расходник / устройство
MED_KINDS = ("medication", "supplement", "supply", "device")
# status факта приёма
INTAKE_STATUSES = ("taken", "missed", "skipped", "rescheduled", "unknown")
# frequency_type расписания
FREQUENCY_TYPES = ("daily", "interval", "weekly")
# food_relation режима приёма (ADR-189): привязка к еде
FOOD_RELATIONS = ("before_meal", "after_meal", "during_meal", "empty_stomach", "independent")
# status курса (ADR-189, фаза C)
COURSE_STATUSES = ("planned", "active", "completed", "paused")


class Medication(Base):
    """Каталог препарата или медицинского расходника."""

    __tablename__ = "medications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # medication | supplement | supply | device
    kind: Mapped[str] = mapped_column(String(20), default="medication", nullable=False)
    active_ingredient: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    analogues: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    form: Mapped[str | None] = mapped_column(String(50), nullable=True)  # tablet/capsule/liquid/cream/...
    strength: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "500 mg"
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prescription_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    storage_conditions: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)  # mg / ml / tablet / pcs
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)  # как принимать
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_inventory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # ADR-190 (фаза E): явное разрешение превышать суточный предел компонентов
    allow_ul_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    components: Mapped[list[MedComponent]] = relationship(
        "MedComponent", lazy="selectin", order_by="MedComponent.sort_order"
    )
    variants: Mapped[list[MedVariant]] = relationship("MedVariant", lazy="selectin", order_by="MedVariant.sort_order")

    def __repr__(self) -> str:
        return f"<Medication(id={self.id}, name={self.name!r})>"


class MedKit(Base):
    """Аптечка / место хранения."""

    __tablename__ = "med_kits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    linked_location: Mapped[TaskLocation | None] = relationship("TaskLocation", lazy="selectin")

    def __repr__(self) -> str:
        return f"<MedKit(id={self.id}, name={self.name!r})>"


class MedSubstance(Base):
    """Канонический «активный элемент» (ADR-190): ключ группировки/поиска/замены.

    Один препарат = 1..N компонентов (med_components); МНН живёт здесь.
    norm_key уникален — дедупликация написаний (ибупрофен/Ибупрофен).
    """

    __tablename__ = "med_substances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    norm_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    inn: Mapped[str | None] = mapped_column(String(200), nullable=True)  # МНН, справочно
    synonyms: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # суточный предел (фаза G использует для сверки)
    daily_max_amt: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_max_unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    daily_max_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MedSubstance(id={self.id}, name={self.name!r})>"


class MedVariant(Base):
    """Вариант таблетки/единицы внутри одной пачки (ADR-190, фаза E).

    Фемостон 2/10: «белые 1–14» и «серые 15–28» — у каждого свой состав.
    Для обычных препаратов вариантов нет: med_components.variant_id = NULL.
    """

    __tablename__ = "med_variants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    count_per_pack: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    medication: Mapped[Medication] = relationship("Medication", lazy="selectin", overlaps="variants")

    def __repr__(self) -> str:
        return f"<MedVariant(id={self.id}, name={self.name!r})>"


class MedComponent(Base):
    """Компонент состава: препарат ↔ вещество + дозировка (ADR-190)."""

    __tablename__ = "med_components"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("med_variants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    substance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("med_substances.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    medication: Mapped[Medication] = relationship("Medication", lazy="selectin", overlaps="components")
    substance: Mapped[MedSubstance] = relationship("MedSubstance", lazy="selectin")
    variant: Mapped[MedVariant | None] = relationship("MedVariant", lazy="selectin")

    def __repr__(self) -> str:
        return f"<MedComponent(med={self.medication_id}, sub={self.substance_id})>"


class MedStock(Base):
    """Партия препарата: остаток + срок годности, привязана к аптечке."""

    __tablename__ = "med_stocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("med_kits.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    low_stock_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    medication: Mapped[Medication] = relationship("Medication", lazy="selectin")
    kit: Mapped[MedKit | None] = relationship("MedKit", lazy="selectin")

    def __repr__(self) -> str:
        return f"<MedStock(id={self.id}, qty={self.quantity}, expiry={self.expiry_date})>"


class MedCourse(Base):
    """Курс приёма (ADR-189, фаза C): один препарат или комплекс.

    Элементы курса — MedSchedule с course_id (каждый со своим режимом).
    График вычисляется на лету (build_course_plan), MedIntake остаётся журналом фактов.
    """

    __tablename__ = "med_courses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # planned | active | completed | paused
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<MedCourse(id={self.id}, name={self.name!r})>"


class MedSchedule(Base):
    """Курс/расписание приёма: доза + частота (ежедневно / интервал / по дням)."""

    __tablename__ = "med_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dose_quantity: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    dose_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    frequency_type: Mapped[str] = mapped_column(String(20), default="daily", nullable=False)  # daily|interval|weekly
    times_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)  # для daily
    times_of_day: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ["08:00","20:00"]
    interval_hours: Mapped[float | None] = mapped_column(Float, nullable=True)  # для interval
    days_of_week: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [0..6] для weekly (0=Mon)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Режим приёма (ADR-189, миграция 095): семантические параметры "как принимать"
    # food_relation: before/after/during_meal | empty_stomach | independent
    food_relation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # длительность в днях (end = start + duration − 1)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # переопределение времён еды: {"breakfast": "08:00", ...}
    meal_timing: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    # сдвиг относительно еды (минуты)
    meal_offset_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # курс (ADR-189, фаза C): элемент курса
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("med_courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    medication: Mapped[Medication] = relationship("Medication", lazy="selectin")

    def __repr__(self) -> str:
        return f"<MedSchedule(id={self.id}, freq={self.frequency_type})>"


class MedIntake(Base):
    """Факт приёма (или пропуска) по расписанию либо разовый."""

    __tablename__ = "med_intakes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("med_schedules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # ADR-190 (фаза F): приём выполнен заменителем — medication_id = фактический
    # препарат, substituted_for_id = тот, вместо которого он принят
    substituted_for_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("medications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # ADR-190 (фаза G): явное подтверждение превышения суточной дозы
    ul_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # когда должно было быть
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # фактическое время
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # taken | missed | skipped | rescheduled | unknown
    status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    quantity_taken: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", lazy="selectin")
    medication: Mapped[Medication] = relationship("Medication", lazy="selectin", foreign_keys=[medication_id])
    substituted_for: Mapped[Medication | None] = relationship(
        "Medication", lazy="selectin", foreign_keys=[substituted_for_id]
    )
    schedule: Mapped[MedSchedule | None] = relationship("MedSchedule", lazy="selectin")

    def __repr__(self) -> str:
        return f"<MedIntake(id={self.id}, status={self.status})>"
