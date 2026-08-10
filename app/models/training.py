"""TrainingDay model — daily training plan with LLM-generated tasks and subtasks."""

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class TrainingDay(Base):
    """A single day's training plan — groups ActivityLog tasks with subtasks."""

    __tablename__ = "training_days"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )  # optional plan name (e.g. "Morning", "Evening")
    status: Mapped[str] = mapped_column(
        String(20), default="planned", nullable=False
    )  # planned / active / completed / analyzed
    plan_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_day_suggestion: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # JSON — LLM's plan for tomorrow
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<TrainingDay(id={self.id}, date={self.target_date}, status={self.status})>"
