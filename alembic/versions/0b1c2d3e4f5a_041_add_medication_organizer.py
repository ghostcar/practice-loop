"""041_add_medication_organizer — M3 Personal Suite: Medication Organizer (Шаг 11b).

Adds (all relief-only, Private Record — DATA_LIFECYCLE.md):
- ``medications``   — каталог лекарств / БАД / расходников
- ``med_kits``      — аптечки / места хранения
- ``med_stocks``    — партия препарата (остаток + срок годности)
- ``med_schedules`` — курс/расписание приёма
- ``med_intakes``   — факт приёма
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0b1c2d3e4f5a"
down_revision: str | None = "f7a1b2c3d4e5"  # 040_add_mobile_auth_push
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="medication"),
        sa.Column("active_ingredient", sa.String(200), nullable=True),
        sa.Column("form", sa.String(50), nullable=True),
        sa.Column("strength", sa.String(50), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("image_path", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medications_user_id", "medications", ["user_id"])

    op.create_table(
        "med_kits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_med_kits_user_id", "med_kits", ["user_id"])

    op.create_table(
        "med_stocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("medication_id", sa.Uuid(), sa.ForeignKey("medications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kit_id", sa.Uuid(), sa.ForeignKey("med_kits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("lot_number", sa.String(100), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("low_stock_threshold", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_med_stocks_user_id", "med_stocks", ["user_id"])
    op.create_index("ix_med_stocks_medication_id", "med_stocks", ["medication_id"])
    op.create_index("ix_med_stocks_kit_id", "med_stocks", ["kit_id"])

    op.create_table(
        "med_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("medication_id", sa.Uuid(), sa.ForeignKey("medications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dose_quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("dose_unit", sa.String(20), nullable=True),
        sa.Column("frequency_type", sa.String(20), nullable=False, server_default="daily"),
        sa.Column("times_per_day", sa.Integer(), nullable=True),
        sa.Column("times_of_day", sa.JSON(), nullable=True),
        sa.Column("interval_hours", sa.Float(), nullable=True),
        sa.Column("days_of_week", sa.JSON(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_med_schedules_user_id", "med_schedules", ["user_id"])
    op.create_index("ix_med_schedules_medication_id", "med_schedules", ["medication_id"])

    op.create_table(
        "med_intakes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("medication_id", sa.Uuid(), sa.ForeignKey("medications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), sa.ForeignKey("med_schedules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("quantity_taken", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_med_intakes_user_id", "med_intakes", ["user_id"])
    op.create_index("ix_med_intakes_medication_id", "med_intakes", ["medication_id"])
    op.create_index("ix_med_intakes_schedule_id", "med_intakes", ["schedule_id"])


def downgrade() -> None:
    op.drop_index("ix_med_intakes_schedule_id", table_name="med_intakes")
    op.drop_index("ix_med_intakes_medication_id", table_name="med_intakes")
    op.drop_index("ix_med_intakes_user_id", table_name="med_intakes")
    op.drop_table("med_intakes")

    op.drop_index("ix_med_schedules_medication_id", table_name="med_schedules")
    op.drop_index("ix_med_schedules_user_id", table_name="med_schedules")
    op.drop_table("med_schedules")

    op.drop_index("ix_med_stocks_kit_id", table_name="med_stocks")
    op.drop_index("ix_med_stocks_medication_id", table_name="med_stocks")
    op.drop_index("ix_med_stocks_user_id", table_name="med_stocks")
    op.drop_table("med_stocks")

    op.drop_index("ix_med_kits_user_id", table_name="med_kits")
    op.drop_table("med_kits")

    op.drop_index("ix_medications_user_id", table_name="medications")
    op.drop_table("medications")
