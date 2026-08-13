"""028_add_tag_numbers — numbered tag verification for slot closes.

Adds:
- lock_slot_occurrences.close_tag_number (VARCHAR 100, nullable)
- lock_slot_rules.require_tag (BOOLEAN, default False)
- lock_tag_violations table
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7bf818094186"
down_revision: str | None = "1f2f3be8f095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lock_slot_occurrences",
        sa.Column("close_tag_number", sa.String(100), nullable=True),
    )
    op.add_column(
        "lock_slot_rules",
        sa.Column("require_tag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "lock_tag_violations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("slot_occurrence_id", sa.Uuid(), nullable=False),
        sa.Column("expected_tag", sa.String(100), nullable=True),
        sa.Column("provided_tag", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False, server_default=sa.text("'mismatch'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["lock_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slot_occurrence_id"], ["lock_slot_occurrences.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("lock_tag_violations")
    op.drop_column("lock_slot_rules", "require_tag")
    op.drop_column("lock_slot_occurrences", "close_tag_number")
