"""031_add_social_publications — Platform Social S3: immutable redacted snapshots.

Feed reads ONLY this table — never joins private Tracker/Timer tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f"
down_revision: str | None = "8a2c3d4e5f6"  # 030_add_social_relationships
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "social_publications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_id", sa.Uuid(), sa.ForeignKey("social_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default=sa.text("'relationship_only'")),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("subject_namespace", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_publications_owner", "social_publications", ["owner_id"])
    op.create_index("ix_social_publications_subject", "social_publications", ["subject_id"])
    op.create_index("ix_social_publications_namespace", "social_publications", ["subject_namespace"])


def downgrade() -> None:
    op.drop_table("social_publications")
