"""067_inclusive_health_cycle_suite — Inclusive Health & Cycle Calendar expansion.

Adds profile_type, hrt_regimen, emulated_cycle_length, emulated_period_length to cycle_settings.
Adds bbt, session_id, post_session_data to cycle_events and health_states.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "067_inclusive_health_cycle_suite"
down_revision: str | None = "066_add_user_display_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Upgrade cycle_settings
    op.add_column("cycle_settings", sa.Column("profile_type", sa.String(length=30), server_default="natural_menstrual", nullable=False))
    op.add_column("cycle_settings", sa.Column("hrt_regimen", JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("cycle_settings", sa.Column("emulated_cycle_length", sa.Integer(), server_default="28", nullable=False))
    op.add_column("cycle_settings", sa.Column("emulated_period_length", sa.Integer(), server_default="5", nullable=False))

    # Upgrade cycle_events
    op.add_column("cycle_events", sa.Column("bbt", sa.Float(), nullable=True))
    op.add_column("cycle_events", sa.Column("session_id", UUID(as_uuid=True), nullable=True))
    op.add_column("cycle_events", sa.Column("post_session_data", JSONB(astext_type=sa.Text()), nullable=True))

    # Upgrade health_states
    op.add_column("health_states", sa.Column("post_session_drop", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("health_states", sa.Column("skin_sensitivity", sa.Integer(), nullable=True))
    op.add_column("health_states", sa.Column("hrt_taken", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("health_states", "hrt_taken")
    op.drop_column("health_states", "skin_sensitivity")
    op.drop_column("health_states", "post_session_drop")

    op.drop_column("cycle_events", "post_session_data")
    op.drop_column("cycle_events", "session_id")
    op.drop_column("cycle_events", "bbt")

    op.drop_column("cycle_settings", "emulated_period_length")
    op.drop_column("cycle_settings", "emulated_cycle_length")
    op.drop_column("cycle_settings", "hrt_regimen")
    op.drop_column("cycle_settings", "profile_type")
