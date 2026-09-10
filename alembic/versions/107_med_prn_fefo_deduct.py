"""Medication PRN, kit binding and stock deduction fields (ADR-207).

Revision ID: 107_med_prn_fefo_deduct
Revises: 106_omni_pillory_sessions
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "107_med_prn_fefo_deduct"
down_revision: str | None = "106_omni_pillory_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. MedSchedule preferred_kit_id
    op.add_column(
        "med_schedules",
        sa.Column(
            "preferred_kit_id",
            sa.UUID(),
            sa.ForeignKey("med_kits.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_med_schedules_preferred_kit_id", "med_schedules", ["preferred_kit_id"])

    # 2. MedIntake kit_id, stock_id, is_prn
    op.add_column(
        "med_intakes",
        sa.Column(
            "kit_id",
            sa.UUID(),
            sa.ForeignKey("med_kits.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_med_intakes_kit_id", "med_intakes", ["kit_id"])

    op.add_column(
        "med_intakes",
        sa.Column(
            "stock_id",
            sa.UUID(),
            sa.ForeignKey("med_stocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_med_intakes_stock_id", "med_intakes", ["stock_id"])

    op.add_column(
        "med_intakes",
        sa.Column(
            "is_prn",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("med_intakes", "is_prn")
    op.drop_index("ix_med_intakes_stock_id", table_name="med_intakes")
    op.drop_column("med_intakes", "stock_id")
    op.drop_index("ix_med_intakes_kit_id", table_name="med_intakes")
    op.drop_column("med_intakes", "kit_id")

    op.drop_index("ix_med_schedules_preferred_kit_id", table_name="med_schedules")
    op.drop_column("med_schedules", "preferred_kit_id")
