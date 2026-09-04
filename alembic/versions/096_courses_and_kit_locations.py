"""Medication courses + kit locations (ADR-189, phase C).

- med_courses: course header (single medication or a complex of several,
  each with its own regimen via med_schedules.course_id)
- med_schedules.course_id: FK to med_courses (ON DELETE SET NULL)
- med_kits.location_id: FK to task_locations — аптечки привязываются
  к иерархическим локациям (Квартира → комната → место)

Revision ID: 096_courses_kit_locations
Revises: 095_med_regimen_fields
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "096_courses_kit_locations"
down_revision: str | None = "095_med_regimen_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "med_courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_med_courses_user_id", "med_courses", ["user_id"])
    op.add_column(
        "med_schedules",
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("med_courses.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_med_schedules_course_id", "med_schedules", ["course_id"])
    op.add_column(
        "med_kits",
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_med_kits_location_id", "med_kits", ["location_id"])


def downgrade() -> None:
    op.drop_index("ix_med_kits_location_id", table_name="med_kits")
    op.drop_column("med_kits", "location_id")
    op.drop_index("ix_med_schedules_course_id", table_name="med_schedules")
    op.drop_column("med_schedules", "course_id")
    op.drop_index("ix_med_courses_user_id", table_name="med_courses")
    op.drop_table("med_courses")
