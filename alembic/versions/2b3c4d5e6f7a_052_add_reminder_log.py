"""052_add_reminder_log — таблица дедупликации напоминаний (ADR-095).

Reminder engine периодически шлёт напоминания (лекарства/средства/уход/таймер).
Таблица ``reminder_log`` хранит доставленные напоминания, чтобы не слать
одно и то же на каждом цикле. Unique (user_id, kind, dedupe_key).

Relief-only (PD-013): напоминания не применяют очки/штрафы.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b3c4d5e6f7a"
down_revision: str | None = "d3e4f5a6b7c8"  # 051_care_products_cross_module
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminder_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "dedupe_key", name="uq_reminder_log_user_kind_key"),
    )
    op.create_index("ix_reminder_log_user_id", "reminder_log", ["user_id"])
    op.create_index("ix_reminder_log_kind", "reminder_log", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_reminder_log_kind", table_name="reminder_log")
    op.drop_index("ix_reminder_log_user_id", table_name="reminder_log")
    op.drop_table("reminder_log")
