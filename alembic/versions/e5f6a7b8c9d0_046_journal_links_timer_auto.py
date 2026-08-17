"""046_journal_links_timer_auto — Sexual Journal links + Timer auto-entry (Шаг 14b).

Sexual Journal ↔ Tracker/Timer (PRODUCT_OVERVIEW §16, DATA_LIFECYCLE.md — связи по
ID без раскрытия, мягкие ссылки без FK):

- ``sj_entries``:
  - ``status``           — draft (авто-создана, детали не заполнены) | completed
  - ``source``           — manual | activity (из задачи) | timer_slot (из окна таймера)
  - ``activity_log_id``  — мягкая ссылка на задачу Tracker (ActivityLog)
  - ``slot_occurrence_id`` — мягкая ссылка на окно таймера (LockSlotOccurrence)
- ``lock_slot_rules.journal_auto`` — флаг: открытие окна авто-создаёт draft-запись
  журнала (детали пользователь обязан внести при закрытии).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"  # 045_add_sexual_journal
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sj_entries", sa.Column("status", sa.String(20), nullable=False, server_default="completed"))
    op.add_column("sj_entries", sa.Column("source", sa.String(20), nullable=False, server_default="manual"))
    op.add_column("sj_entries", sa.Column("activity_log_id", sa.Uuid(), nullable=True))
    op.add_column("sj_entries", sa.Column("slot_occurrence_id", sa.Uuid(), nullable=True))
    op.create_index("ix_sj_entries_status", "sj_entries", ["status"])

    op.add_column("lock_slot_rules", sa.Column("journal_auto", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("lock_slot_rules", "journal_auto")

    op.drop_index("ix_sj_entries_status", table_name="sj_entries")
    op.drop_column("sj_entries", "slot_occurrence_id")
    op.drop_column("sj_entries", "activity_log_id")
    op.drop_column("sj_entries", "source")
    op.drop_column("sj_entries", "status")
