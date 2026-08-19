"""063_allow_multiple_sessions — снять ограничение «одна активная сессия».

Owner decision (2026-08-19): сессий может быть запущено несколько одновременно
(без механизма дочерних сессий внутри длительной — это отдельная задача).

Migration 013 created the partial unique index ``ix_activity_sessions_one_active``
(``owner_id WHERE status IN ('created','active')``) — one non-ended session per
user. Dropping it allows any number of parallel sessions per user.
"""

from __future__ import annotations

from alembic import op

revision: str = "9c8d7e6f5a4b"
down_revision: str | None = "f0e1d2c3b4a5"  # 062_add_care_place
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_activity_sessions_one_active", table_name="activity_sessions")


def downgrade() -> None:
    op.create_index(
        "ix_activity_sessions_one_active",
        "activity_sessions",
        ["owner_id"],
        unique=True,
        postgresql_where="status IN ('created', 'active')",
    )
