"""Drop dead experimental tables: automation_triggers, user_league_tiers, user_duels.

These three tables were created in 082_add_missing_module_tables but never had
routes, UI, or scheduler wiring (ADR-186). The agent-level helpers that touched
them were prototype-grade (e.g. hardcoded duel scores, auto-applied XP penalty)
and conflicted with the "no auto-escalation" invariant (ADR-106). Tables are
empty in production. Removing them makes the schema honest.

Downgrade recreates the exact schema from the removed models so the change is
fully reversible.

Revision ID: 094_drop_dead_experimental
Revises: 093_portal_selection
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "094_drop_dead_experimental"
down_revision: str | None = "093_portal_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF EXISTS: on a fresh bootstrap 082 no longer creates these tables (their
    # models are deleted), so they may be absent; on the real upgrade path they
    # exist since 082 ran with the old code. Both paths must succeed.
    op.execute("DROP TABLE IF EXISTS automation_triggers")
    op.execute("DROP TABLE IF EXISTS user_league_tiers")
    op.execute("DROP TABLE IF EXISTS user_duels")


def downgrade() -> None:
    op.create_table(
        "automation_triggers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("condition_type", sa.String(length=50), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False, server_default=sa.text("2.0")),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("action_params", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_agent_generated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reasoning_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_automation_triggers_user_id", "automation_triggers", ["user_id"])

    op.create_table(
        "user_league_tiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "community_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("communities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "league_tier",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'bronze'"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("community_id", "user_id", name="uq_community_user_league"),
    )
    op.create_index("ix_user_league_tiers_community_id", "user_league_tiers", ["community_id"])
    op.create_index("ix_user_league_tiers_user_id", "user_league_tiers", ["user_id"])

    op.create_table(
        "user_duels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "challenger_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opponent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("challenger_score", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("opponent_score", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("winner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_duels_challenger_id", "user_duels", ["challenger_id"])
    op.create_index("ix_user_duels_opponent_id", "user_duels", ["opponent_id"])
