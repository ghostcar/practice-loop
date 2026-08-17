"""056_add_aftercare_entries — отдельный модуль Aftercare (C1).

``aftercare_entries`` — структурированный журнал заботы после сцены
(физическая/эмоциональная/дебриф/гидратация/отдых). Relief-only (PD-013),
мягкие связи с Sexual Journal (FK SET NULL) и Chastity Timer (по ID).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"  # 055_add_chastity_check_ins
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aftercare_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timer_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("comfort_level", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["sj_entries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_aftercare_entries_user_id", "aftercare_entries", ["user_id"])
    op.create_index("ix_aftercare_entries_entry_date", "aftercare_entries", ["entry_date"])
    op.create_index("ix_aftercare_entries_journal_entry_id", "aftercare_entries", ["journal_entry_id"])
    op.create_index("ix_aftercare_entries_timer_session_id", "aftercare_entries", ["timer_session_id"])
    op.create_index("ix_aftercare_entries_kind", "aftercare_entries", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_aftercare_entries_kind", table_name="aftercare_entries")
    op.drop_index("ix_aftercare_entries_timer_session_id", table_name="aftercare_entries")
    op.drop_index("ix_aftercare_entries_journal_entry_id", table_name="aftercare_entries")
    op.drop_index("ix_aftercare_entries_entry_date", table_name="aftercare_entries")
    op.drop_index("ix_aftercare_entries_user_id", table_name="aftercare_entries")
    op.drop_table("aftercare_entries")
