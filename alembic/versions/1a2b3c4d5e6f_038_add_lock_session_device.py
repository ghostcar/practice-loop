\"\"\"038 — LockTimer device inventory (Step 8, ADR-076).

lock_sessions.device_id — optional physical device (inventory item) bound to
a lock session. Nullable, SET NULL on inventory item delete, indexed.
\"\"\"

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "1a2b3c4d5e6f"
down_revision: str | None = "0a1b2c3d4e5f"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("lock_sessions", sa.Column("device_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_lock_sessions_device_id_inventory_items",
        "lock_sessions",
        "inventory_items",
        ["device_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_lock_sessions_device_id", "lock_sessions", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_lock_sessions_device_id", table_name="lock_sessions")
    op.drop_constraint("fk_lock_sessions_device_id_inventory_items", "lock_sessions", type_="foreignkey")
    op.drop_column("lock_sessions", "device_id")
