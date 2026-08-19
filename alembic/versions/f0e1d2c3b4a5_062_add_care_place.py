"""062_add_care_place — место проведения процедуры ухода.

Owner decision (2026-08-19): в личном контуре, в блоке ухода и процедур, должно быть
место проведения (салон, название, может быть адрес) и показываться пользователю.

Adds to ``care_routines``, ``care_entries`` and ``care_courses``:
- ``place_name``: название места (например салон) — String(200), nullable;
- ``place_address``: адрес — String(300), nullable.

Safe defaults: both NULL for existing rows (место не было известно).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "f0e1d2c3b4a5"
down_revision: str | None = "d1e2f3a4b5c6"  # 061_add_entity_safety_contract
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("care_routines", "care_entries", "care_courses"):
        op.add_column(table, sa.Column("place_name", sa.String(length=200), nullable=True))
        op.add_column(table, sa.Column("place_address", sa.String(length=300), nullable=True))


def downgrade() -> None:
    for table in ("care_routines", "care_entries", "care_courses"):
        op.drop_column(table, "place_address")
        op.drop_column(table, "place_name")
