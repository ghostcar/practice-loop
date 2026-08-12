"""030_add_social_relationships — Platform Social S2: relationships, blocks, grants, notifications.

Invitation lifecycle (pending→accepted/declined/expired/revoked),
cross-product blocks, scoped capability grants, notification outbox.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "030_add_social_relationships"
down_revision: str | None = "5d1f9a8b2c3e"  # 029_add_social_foundation
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # social_relationships
    op.create_table(
        "social_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requester_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("display_role", sa.String(20), nullable=False, server_default=sa.text("'viewer'")),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requester_id", "recipient_id", name="uq_social_relationship_pair"),
    )
    op.create_index("ix_social_relationships_requester", "social_relationships", ["requester_id"])
    op.create_index("ix_social_relationships_recipient", "social_relationships", ["recipient_id"])

    # social_blocks
    op.create_table(
        "social_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("blocker_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blocked_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_social_block_pair"),
    )
    op.create_index("ix_social_blocks_blocker", "social_blocks", ["blocker_id"])
    op.create_index("ix_social_blocks_blocked", "social_blocks", ["blocked_id"])

    # social_grants
    op.create_table(
        "social_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("relationship_id", sa.Uuid(), sa.ForeignKey("social_relationships.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(20), nullable=False, server_default=sa.text("'subject'")),
        sa.Column("scope_namespace", sa.String(80), nullable=True),
        sa.Column("subject_id", sa.Uuid(), sa.ForeignKey("social_subjects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("caps", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'proposed'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_grants_relationship", "social_grants", ["relationship_id"])
    op.create_index("ix_social_grants_subject", "social_grants", ["subject_id"])

    # social_notifications
    op.create_table(
        "social_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_notifications_user", "social_notifications", ["user_id"])


def downgrade() -> None:
    op.drop_table("social_notifications")
    op.drop_table("social_grants")
    op.drop_table("social_blocks")
    op.drop_table("social_relationships")
