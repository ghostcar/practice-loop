"""035_add_template_sort_order — template reordering on /locktimer/templates.

Adds:
- lock_timer_templates.sort_order (INTEGER, NOT NULL, default 0)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d"
down_revision: str | None = "d4e5f6a7b8c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lock_timer_templates",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("lock_timer_templates", "sort_order")
