"""061_add_entity_safety_contract — ADR-105 typed safety contract on Entity.

Adds the physical storage agreed in ADR-105 for the 18+ catalog:
- ``safety_contract``: typed JSONB (eligibility/risk/safety/evidence/gamification/source);
- ``automation_allowed``: explicit automation gate, default false (nothing automated);
- ``adult_only``: marks adult-only content, default false;
- ``content_status``: editorial status (not_assessed/draft/reviewed/approved/rejected);
- ``content_version``: monotonic content revision, default 1.

Safe defaults for existing rows: automation off, adult_only false, not_assessed.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c1d2e3f4a5b6"  # 060_add_activity_session_history
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entities", sa.Column("safety_contract", postgresql.JSONB(), nullable=True))
    op.add_column(
        "entities",
        sa.Column("automation_allowed", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("entities", sa.Column("adult_only", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column(
        "entities",
        sa.Column("content_status", sa.String(length=20), nullable=False, server_default="not_assessed"),
    )
    op.add_column("entities", sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_entities_content_status", "entities", ["content_status"])


def downgrade() -> None:
    op.drop_index("ix_entities_content_status", table_name="entities")
    op.drop_column("entities", "content_version")
    op.drop_column("entities", "content_status")
    op.drop_column("entities", "adult_only")
    op.drop_column("entities", "automation_allowed")
    op.drop_column("entities", "safety_contract")
