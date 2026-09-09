"""Lock timer permanent freeze and unfreeze (ADR-199).

Revision ID: 104_lock_timer_freeze
Revises: 103_lock_extensions_games
Create Date: 2026-09-09
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "104_lock_timer_freeze"
down_revision: str | None = "103_lock_extensions_games"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lock_sessions",
        sa.Column("is_frozen", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "lock_sessions",
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "lock_sessions",
        sa.Column("frozen_remaining_seconds", sa.Integer(), nullable=True),
    )

    # Seed wear_event_definitions for timer freeze/unfreeze
    conn = op.get_bind()
    defs = [
        {
            "id": uuid.uuid4(),
            "code": "timer_freeze",
            "title": "Перманентная заморозка таймера",
            "category": "timer",
            "is_valid_reason": True,
            "trigger_config": {"freeze_timer": True},
        },
        {
            "id": uuid.uuid4(),
            "code": "timer_unfreeze",
            "title": "Разморозка таймера",
            "category": "timer",
            "is_valid_reason": True,
            "trigger_config": {"unfreeze_timer": True},
        },
    ]
    for d in defs:
        conn.execute(
            sa.text(
                """
                INSERT INTO wear_event_definitions (id, code, title, category, is_valid_reason, default_duration_minutes, trigger_config, is_active, created_at, updated_at)
                VALUES (:id, :code, :title, :category, :is_valid_reason, NULL, :trigger_config, true, NOW(), NOW())
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": d["id"],
                "code": d["code"],
                "title": d["title"],
                "category": d["category"],
                "is_valid_reason": d["is_valid_reason"],
                "trigger_config": json.dumps(d["trigger_config"]),
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM wear_event_definitions WHERE code IN ('timer_freeze', 'timer_unfreeze')")
    )
    op.drop_column("lock_sessions", "frozen_remaining_seconds")
    op.drop_column("lock_sessions", "frozen_at")
    op.drop_column("lock_sessions", "is_frozen")
