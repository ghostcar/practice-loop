"""Add store_raw_response flag to llm_provider_configs.

Implements REMEDIATION_SPEC.md §7.5: per-config opt-in/opt-out of debug payload retention.
Default True to preserve ADR-034 backwards-compat. Users disable to protect privacy.
Also adds ActivityLog.expires_at column — opt-in TTL on raw_llm_response.

Revision ID: 016
Revises: 015_add_training_log_entries
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_provider_configs",
        sa.Column(
            "store_raw_response",
            sa.Boolean,
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "activity_logs",
        sa.Column(
            "raw_response_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_activity_logs_raw_response_expires_at",
        "activity_logs",
        ["raw_response_expires_at"],
        postgresql_where=sa.text("raw_response_expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_activity_logs_raw_response_expires_at", table_name="activity_logs")
    op.drop_column("activity_logs", "raw_response_expires_at")
    op.drop_column("llm_provider_configs", "store_raw_response")
