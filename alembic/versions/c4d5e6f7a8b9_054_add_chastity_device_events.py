"""054_add_chastity_device_events — уход за устройством (комфорт/проблемы/обслуживание), B2.

``chastity_device_events`` — журнал ухода за физическим устройством во время
ношения (PRODUCT_OVERVIEW §6.2). Мягкие ссылки: device_id → inventory_items
(SET NULL), session_id → lock_sessions (SET NULL). Relief-only (PD-013).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "9a8b7c6d5e4f"  # 053_add_care_courses
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chastity_device_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("lock_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("comfort_level", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chastity_device_events_user_id", "chastity_device_events", ["user_id"])
    op.create_index("ix_chastity_device_events_device_id", "chastity_device_events", ["device_id"])
    op.create_index("ix_chastity_device_events_session_id", "chastity_device_events", ["session_id"])
    op.create_index("ix_chastity_device_events_event_type", "chastity_device_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_chastity_device_events_event_type", table_name="chastity_device_events")
    op.drop_index("ix_chastity_device_events_session_id", table_name="chastity_device_events")
    op.drop_index("ix_chastity_device_events_device_id", table_name="chastity_device_events")
    op.drop_index("ix_chastity_device_events_user_id", table_name="chastity_device_events")
    op.drop_table("chastity_device_events")
