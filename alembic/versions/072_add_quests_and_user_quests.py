"""072_add_quests_and_user_quests — Quests and Gamification Challenges tables.

Adds quests and user_quests tables for daily/weekly practice quests and streak rewards.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "072_quests_user_quests"
down_revision: str | None = "071_partner_profiles_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "quests" not in tables:
        op.create_table(
            "quests",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(length=500), nullable=False),
            sa.Column("quest_type", sa.String(length=50), server_default="daily", nullable=False),
            sa.Column("category", sa.String(length=50), server_default="general", nullable=False),
            sa.Column("target_count", sa.Integer(), server_default="1", nullable=False),
            sa.Column("reward_xp", sa.Integer(), server_default="100", nullable=False),
            sa.Column("badge_icon", sa.String(length=50), server_default="trophy", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

    if "user_quests" not in tables:
        op.create_table(
            "user_quests",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("quest_id", UUID(as_uuid=True), sa.ForeignKey("quests.id", ondelete="CASCADE"), nullable=False),
            sa.Column("current_progress", sa.Integer(), server_default="0", nullable=False),
            sa.Column("status", sa.String(length=50), server_default="active", nullable=False),
            sa.Column("obtained_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        op.create_index("ix_user_quests_user_id", "user_quests", ["user_id"])
        op.create_index("ix_user_quests_quest_id", "user_quests", ["quest_id"])


def downgrade() -> None:
    op.drop_table("user_quests")
    op.drop_table("quests")
