"""Wear open-ended events & LockSession mode (ADR-195).

Creates:
- `wear_event_definitions`: registry of open-ended wear events (hygiene, care, sport, sex, inspection, etc.)
- `wear_event_logs`: log of wear events with exact second timestamps and reaction audits
- Updates `lock_sessions` with `mode`, `is_currently_locked`, `current_tag_number`,
  `last_wear_checkin_at`, `last_comfort_score`, `pending_open_event_id`.

Revision ID: 100_wear_open_ended_events
Revises: 099_llm_call_logs
Create Date: 2026-09-09
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "100_wear_open_ended_events"
down_revision: str | None = "099_llm_call_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return UUID(as_uuid=True)
    return sa.Uuid()


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    uuid_col = _uuid_type()
    json_col = _json_type()

    # 1. wear_event_definitions
    op.create_table(
        "wear_event_definitions",
        sa.Column("id", uuid_col, primary_key=True, default=uuid.uuid4),
        sa.Column(
            "owner_id",
            uuid_col,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("code", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("is_valid_reason", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("default_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("trigger_config", json_col, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 2. wear_event_logs
    op.create_table(
        "wear_event_logs",
        sa.Column("id", uuid_col, primary_key=True, default=uuid.uuid4),
        sa.Column(
            "user_id",
            uuid_col,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "device_id",
            uuid_col,
            sa.ForeignKey("inventory_items.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "session_id",
            uuid_col,
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("event_code", sa.String(50), nullable=False, index=True),
        sa.Column(
            "event_def_id",
            uuid_col,
            sa.ForeignKey("wear_event_definitions.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("state_before", sa.String(20), nullable=False),
        sa.Column("state_after", sa.String(20), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_relock_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("comfort_score", sa.Integer(), nullable=True),
        sa.Column("tag_number", sa.String(50), nullable=True),
        sa.Column("user_comment", sa.Text(), nullable=True),
        sa.Column("llm_analysis", sa.Text(), nullable=True),
        sa.Column("reactions_applied", json_col, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )

    # 3. lock_sessions additions
    op.add_column("lock_sessions", sa.Column("mode", sa.String(20), nullable=False, server_default="scheduled"))
    op.add_column("lock_sessions", sa.Column("is_currently_locked", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("lock_sessions", sa.Column("current_tag_number", sa.String(50), nullable=True))
    op.add_column("lock_sessions", sa.Column("last_wear_checkin_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lock_sessions", sa.Column("last_comfort_score", sa.Integer(), nullable=True))
    op.add_column(
        "lock_sessions",
        sa.Column(
            "pending_open_event_id",
            uuid_col,
            sa.ForeignKey("wear_event_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 4. Seed default event definitions
    conn = op.get_bind()
    seed_defs = [
        {
            "id": uuid.uuid4(),
            "code": "hygiene_quick",
            "title": "Санитарная обработка",
            "category": "hygiene",
            "is_valid_reason": True,
            "default_duration_minutes": 10,
            "trigger_config": {"strict_delay_penalty": True, "overtime_penalty_per_min": 10},
        },
        {
            "id": uuid.uuid4(),
            "code": "care_grooming",
            "title": "Уходовые процедуры / Депиляция",
            "category": "care",
            "is_valid_reason": True,
            "default_duration_minutes": 60,
            "trigger_config": {"create_care_task": True},
        },
        {
            "id": uuid.uuid4(),
            "code": "sport_workout",
            "title": "Спорт / Интенсивная тренировка",
            "category": "sport",
            "is_valid_reason": True,
            "default_duration_minutes": 90,
            "trigger_config": {"modify_training_plan": True},
        },
        {
            "id": uuid.uuid4(),
            "code": "sex_activity",
            "title": "Секс / Близость",
            "category": "sex",
            "is_valid_reason": True,
            "default_duration_minutes": 120,
            "trigger_config": {"record_sexual_journal": True},
        },
        {
            "id": uuid.uuid4(),
            "code": "force_majeure",
            "title": "Форс-мажор (Острая боль / Травма / Врач)",
            "category": "force_majeure",
            "is_valid_reason": True,
            "default_duration_minutes": None,
            "trigger_config": {"alert_keyholder": True},
        },
        {
            "id": uuid.uuid4(),
            "code": "breach_relapse",
            "title": "Срыв / Несанкционированное снятие",
            "category": "breach",
            "is_valid_reason": False,
            "default_duration_minutes": None,
            "trigger_config": {"apply_penalty": True},
        },
        {
            "id": uuid.uuid4(),
            "code": "seal_inspection",
            "title": "Проверка пломбы / Бирки (без снятия)",
            "category": "inspection",
            "is_valid_reason": True,
            "default_duration_minutes": None,
            "trigger_config": {"no_unlock": True, "record_checkin": True},
        },
        {
            "id": uuid.uuid4(),
            "code": "orgasm_release",
            "title": "Оргазм / Эякуляция",
            "category": "orgasm",
            "is_valid_reason": True,
            "default_duration_minutes": None,
            "trigger_config": {"record_orgasm": True},
        },
    ]
    for item in seed_defs:
        conn.execute(
            sa.text(
                """
                INSERT INTO wear_event_definitions (id, code, title, category, is_valid_reason, default_duration_minutes, trigger_config, is_active, created_at, updated_at)
                VALUES (:id, :code, :title, :category, :is_valid_reason, :default_duration_minutes, :trigger_config, true, NOW(), NOW())
                """
            ),
            {
                "id": item["id"],
                "code": item["code"],
                "title": item["title"],
                "category": item["category"],
                "is_valid_reason": item["is_valid_reason"],
                "default_duration_minutes": item["default_duration_minutes"],
                "trigger_config": json.dumps(item["trigger_config"]),
            },
        )


def downgrade() -> None:
    op.drop_column("lock_sessions", "pending_open_event_id")
    op.drop_column("lock_sessions", "last_comfort_score")
    op.drop_column("lock_sessions", "last_wear_checkin_at")
    op.drop_column("lock_sessions", "current_tag_number")
    op.drop_column("lock_sessions", "is_currently_locked")
    op.drop_column("lock_sessions", "mode")
    op.drop_table("wear_event_logs")
    op.drop_table("wear_event_definitions")
