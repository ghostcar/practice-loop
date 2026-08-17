"""044_add_health_cycle — M3 Personal Suite: Health + Cycle foundation (Шаг 13, ROADMAP §7 4D).

Adds (all relief-only, Private Record — DATA_LIFECYCLE.md):
- ``health_states``  — ежедневный check-in: настроение, энергия, сон, симптомы, восстановление
- ``lab_records``    — лабораторные записи с оригинальным диапазоном лаборатории
- ``cycle_settings`` — настройки Cycle (одна строка на пользователя)
- ``cycle_events``   — факты Cycle: кровотечение, симптомы, состояние, тесты, наблюдения
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"  # 043_med_migration_source
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "health_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("mood", sa.Integer(), nullable=True),
        sa.Column("energy", sa.Integer(), nullable=True),
        sa.Column("sleep_hours", sa.Float(), nullable=True),
        sa.Column("sleep_quality", sa.Integer(), nullable=True),
        sa.Column("recovery", sa.Integer(), nullable=True),
        sa.Column("symptoms", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_health_states_user_id", "health_states", ["user_id"])
    op.create_index("ix_health_states_event_date", "health_states", ["event_date"])

    op.create_table(
        "lab_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("measured_at", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("ref_min", sa.Float(), nullable=True),
        sa.Column("ref_max", sa.Float(), nullable=True),
        sa.Column("lab_name", sa.String(200), nullable=True),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_records_user_id", "lab_records", ["user_id"])
    op.create_index("ix_lab_records_measured_at", "lab_records", ["measured_at"])

    op.create_table(
        "cycle_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_length", sa.Integer(), nullable=False, server_default="28"),
        sa.Column("period_length", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("contraception", sa.String(20), nullable=False, server_default="none"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cycle_settings_user_id", "cycle_settings", ["user_id"], unique=True)

    op.create_table(
        "cycle_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("value", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cycle_events_user_id", "cycle_events", ["user_id"])
    op.create_index("ix_cycle_events_event_date", "cycle_events", ["event_date"])


def downgrade() -> None:
    op.drop_index("ix_cycle_events_event_date", table_name="cycle_events")
    op.drop_index("ix_cycle_events_user_id", table_name="cycle_events")
    op.drop_table("cycle_events")

    op.drop_index("ix_cycle_settings_user_id", table_name="cycle_settings")
    op.drop_table("cycle_settings")

    op.drop_index("ix_lab_records_measured_at", table_name="lab_records")
    op.drop_index("ix_lab_records_user_id", table_name="lab_records")
    op.drop_table("lab_records")

    op.drop_index("ix_health_states_event_date", table_name="health_states")
    op.drop_index("ix_health_states_user_id", table_name="health_states")
    op.drop_table("health_states")
