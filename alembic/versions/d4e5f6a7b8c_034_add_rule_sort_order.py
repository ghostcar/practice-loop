"""034_add_rule_sort_order — drag&drop rule ordering for LockTimer drafts.

Adds:
- lock_slot_rules.sort_order (INTEGER, NOT NULL, default 0)
- lock_task_rules.sort_order (INTEGER, NOT NULL, default 0)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c"
down_revision: str | None = "c3d4e5f6a7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lock_slot_rules",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "lock_task_rules",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("lock_task_rules", "sort_order")
    op.drop_column("lock_slot_rules", "sort_order")
