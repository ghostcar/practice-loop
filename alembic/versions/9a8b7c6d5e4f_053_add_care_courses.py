"""053_add_care_courses — курсы процедур (серии сеансов), ADR-095.

``care_courses`` — курс из N сеансов (лазер/массаж/пилинг) с интервалом.
``care_course_sessions`` — сеансы: номер, дата, статус, мягкая ссылка на запись
ухода (care_entries). Relief-only (PD-013): без игровой интеграции.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a8b7c6d5e4f"
down_revision: str | None = "2b3c4d5e6f7a"  # 052_add_reminder_log
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "care_courses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_item_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("area", sa.String(length=20), server_default="other", nullable=False),
        sa.Column("total_sessions", sa.Integer(), server_default="1", nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(
        "fk_care_courses_catalog_item",
        "care_courses",
        "activity_catalog",
        ["catalog_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_care_courses_user_id", "care_courses", ["user_id"])
    op.create_index("ix_care_courses_catalog_item_id", "care_courses", ["catalog_item_id"])

    op.create_table(
        "care_course_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), sa.ForeignKey("care_courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_number", sa.Integer(), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("entry_id", sa.Uuid(), sa.ForeignKey("care_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_course_sessions_course_id", "care_course_sessions", ["course_id"])
    op.create_index("ix_care_course_sessions_scheduled_date", "care_course_sessions", ["scheduled_date"])


def downgrade() -> None:
    op.drop_index("ix_care_course_sessions_scheduled_date", table_name="care_course_sessions")
    op.drop_index("ix_care_course_sessions_course_id", table_name="care_course_sessions")
    op.drop_table("care_course_sessions")

    op.drop_index("ix_care_courses_catalog_item_id", table_name="care_courses")
    op.drop_index("ix_care_courses_user_id", table_name="care_courses")
    op.drop_constraint("fk_care_courses_catalog_item", "care_courses", type_="foreignkey")
    op.drop_table("care_courses")
