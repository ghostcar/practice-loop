"""047_add_personal_care — M3 Personal Suite: Personal Care (Шаг 15, ROADMAP §7 4B).

Adds (all relief-only, Private Record — DATA_LIFECYCLE.md):
- ``care_routines`` — каталог процедур/рутин ухода (зона, тип, частота, заметки)
- ``care_entries``  — факты выполнения процедуры (дата, длительность, реакция
  кожи, заметки, снимок расчётной фазы Cycle)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"  # 046_journal_links_timer_auto
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "care_routines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("area", sa.String(20), nullable=False, server_default="other"),
        sa.Column("kind", sa.String(20), nullable=False, server_default="home"),
        sa.Column("frequency_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_routines_user_id", "care_routines", ["user_id"])

    op.create_table(
        "care_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("routine_id", sa.Uuid(), sa.ForeignKey("care_routines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("skin_reaction", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cycle_phase", sa.String(20), nullable=True),
        sa.Column("cycle_day", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_entries_user_id", "care_entries", ["user_id"])
    op.create_index("ix_care_entries_entry_date", "care_entries", ["entry_date"])


def downgrade() -> None:
    op.drop_index("ix_care_entries_entry_date", table_name="care_entries")
    op.drop_index("ix_care_entries_user_id", table_name="care_entries")
    op.drop_table("care_entries")

    op.drop_index("ix_care_routines_user_id", table_name="care_routines")
    op.drop_table("care_routines")
