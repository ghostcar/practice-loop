"""045_add_sexual_journal — M3 Personal Suite: Sexual Journal (Шаг 14, ROADMAP §7 4A).

Adds (all relief-only, Private Record — DATA_LIFECYCLE.md):
- ``sj_partners`` — локальные псевдонимы партнёров (никогда не раскрываются наружу);
- ``sj_entries``  — записи журнала: вид активности, дата/длительность, желание и
  возбуждение до начала, защита/контрацепция, оргазмы, интенсивность,
  удовлетворённость, реакции, эмоциональное состояние, aftercare, личные заметки,
  снимок расчётной фазы Cycle и мягкие связи с Timer/Health по ID (без FK).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"  # 044_add_health_cycle
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sj_partners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sj_partners_user_id", "sj_partners", ["user_id"])

    op.create_table(
        "sj_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), sa.ForeignKey("sj_partners.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_type", sa.String(100), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("desire_before", sa.Integer(), nullable=True),
        sa.Column("arousal_before", sa.Integer(), nullable=True),
        sa.Column("protection", sa.String(20), nullable=False, server_default="none"),
        sa.Column("orgasms", sa.Integer(), nullable=True),
        sa.Column("intensity", sa.Integer(), nullable=True),
        sa.Column("satisfaction", sa.Integer(), nullable=True),
        sa.Column("pleasure", sa.Integer(), nullable=True),
        sa.Column("reactions", sa.JSON(), nullable=True),
        sa.Column("emotional_state", sa.JSON(), nullable=True),
        sa.Column("aftercare", sa.Text(), nullable=True),
        sa.Column("recovery", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("timer_session_id", sa.Uuid(), nullable=True),
        sa.Column("health_state_id", sa.Uuid(), nullable=True),
        sa.Column("cycle_phase", sa.String(20), nullable=True),
        sa.Column("cycle_day", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sj_entries_user_id", "sj_entries", ["user_id"])
    op.create_index("ix_sj_entries_entry_date", "sj_entries", ["entry_date"])


def downgrade() -> None:
    op.drop_index("ix_sj_entries_entry_date", table_name="sj_entries")
    op.drop_index("ix_sj_entries_user_id", table_name="sj_entries")
    op.drop_table("sj_entries")

    op.drop_index("ix_sj_partners_user_id", table_name="sj_partners")
    op.drop_table("sj_partners")
