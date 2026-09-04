"""Medication regimen fields on med_schedules (ADR-189, phase B).

Adds semantic regimen parameters to med_schedules so that "how to take"
becomes structured data instead of free text:

- food_relation      — before_meal / after_meal / during_meal / empty_stomach / independent
- duration_days      — course duration in days (end_date = start_date + duration - 1)
- meal_timing        — optional override of default meal times (JSON)
- meal_offset_min    — intake offset relative to meals (minutes; preset defaults)

Courses (med_courses + med_schedules.course_id) land in a later migration
(phase C of ADR-189) — this migration stays limited to regimen fields.

Revision ID: 095_med_regimen_fields
Revises: 094_drop_dead_experimental
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "095_med_regimen_fields"
down_revision: str | None = "094_drop_dead_experimental"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("med_schedules", sa.Column("food_relation", sa.String(length=20), nullable=True))
    op.add_column("med_schedules", sa.Column("duration_days", sa.Integer(), nullable=True))
    op.add_column(
        "med_schedules",
        sa.Column("meal_timing", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("med_schedules", sa.Column("meal_offset_min", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("med_schedules", "meal_offset_min")
    op.drop_column("med_schedules", "meal_timing")
    op.drop_column("med_schedules", "duration_days")
    op.drop_column("med_schedules", "food_relation")
