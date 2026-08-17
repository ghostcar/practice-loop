"""057_add_consent_records — согласия на чувствительную обработку (C3).

``consent_records`` — журнал явных согласий (granted/revoked) на расширенный
LLM-режим, фото-верификацию, обработку данных. Каждое изменение — новая
версия (не перезаписывается). Relief-only (PD-013).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "e6f7a8b9c0d1"  # 056_add_aftercare_entries
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consent_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])
    op.create_index("ix_consent_records_consent_type", "consent_records", ["consent_type"])
    op.create_index("ix_consent_records_state", "consent_records", ["state"])


def downgrade() -> None:
    op.drop_index("ix_consent_records_state", table_name="consent_records")
    op.drop_index("ix_consent_records_consent_type", table_name="consent_records")
    op.drop_index("ix_consent_records_user_id", table_name="consent_records")
    op.drop_table("consent_records")
