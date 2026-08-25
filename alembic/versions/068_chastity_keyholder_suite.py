"""068_chastity_keyholder_suite — Chaster.app style Chastity & Keyholder expansion.

Adds chastity_device_id, keyholder_type, auto_pause_on_health_drop, extension_history to lock_slot_rules and lock_sessions.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "068_chastity_keyholder_suite"
down_revision: str | None = "067_inclusive_health_cycle_suite"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Upgrade lock_slot_rules
    op.add_column(
        "lock_slot_rules",
        sa.Column(
            "chastity_device_id",
            UUID(as_uuid=True),
            sa.ForeignKey("inventory_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "lock_slot_rules", sa.Column("keyholder_type", sa.String(length=30), server_default="llm_bot", nullable=False)
    )
    op.add_column(
        "lock_slot_rules", sa.Column("auto_pause_on_health_drop", sa.Boolean(), server_default="true", nullable=False)
    )
    op.add_column("lock_slot_rules", sa.Column("extension_history", JSONB(astext_type=sa.Text()), nullable=True))

    # Upgrade lock_sessions
    op.add_column(
        "lock_sessions",
        sa.Column(
            "chastity_device_id",
            UUID(as_uuid=True),
            sa.ForeignKey("inventory_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "lock_sessions", sa.Column("keyholder_type", sa.String(length=30), server_default="llm_bot", nullable=False)
    )
    op.add_column("lock_sessions", sa.Column("is_health_paused", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("lock_sessions", "is_health_paused")
    op.drop_column("lock_sessions", "keyholder_type")
    op.drop_column("lock_sessions", "chastity_device_id")

    op.drop_column("lock_slot_rules", "extension_history")
    op.drop_column("lock_slot_rules", "auto_pause_on_health_drop")
    op.drop_column("lock_slot_rules", "keyholder_type")
    op.drop_column("lock_slot_rules", "chastity_device_id")
