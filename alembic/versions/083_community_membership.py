"""Add community membership & visibility columns + missing module tables.

Extends communities with public/private visibility, approval workflow and
invite codes; adds the community_members join table (owner/member, pending/
active/revoked) that powers join/leave/approval.  Also creates the two
module tables added by the un-committed DMS/media-exposure work that never
received a migration (dead_mans_switch_rules, media_exposure_drops).

Revision ID: 083_community_membership
Revises: 082_add_missing_module_tables
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models import Base  # noqa: F401 — imports all modules, registers tables

revision: str = "083_community_membership"
down_revision: str | None = "082_add_missing_module_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that exist in models but not yet in the DB.
MISSING_TABLES = [
    "community_members",
    "dead_mans_switch_rules",
    "media_exposure_drops",
]


def _has_column(conn, table: str, column: str) -> bool:
    res = conn.execute(
        sa.text("SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
        {"t": table, "c": column},
    )
    return res.scalar_one_or_none() is not None


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "communities", "visibility"):
        op.add_column(
            "communities",
            sa.Column("visibility", sa.String(length=20), server_default="public", nullable=False),
        )
    if not _has_column(bind, "communities", "require_approval"):
        op.add_column(
            "communities",
            sa.Column("require_approval", sa.Boolean(), server_default=sa.false(), nullable=False),
        )
    if not _has_column(bind, "communities", "invite_code"):
        op.add_column("communities", sa.Column("invite_code", sa.String(length=64), nullable=True))
    try:
        op.create_index(op.f("ix_communities_invite_code"), "communities", ["invite_code"], unique=False)
    except Exception:
        bind.rollback()

    # Create missing tables from the live model metadata (FK-sorted, idempotent).
    with op.get_context().autocommit_block():
        tables = [Base.metadata.tables[name] for name in MISSING_TABLES if name in Base.metadata.tables]
        Base.metadata.create_all(bind=op.get_bind(), tables=tables, checkfirst=True)

    # Backfill: existing communities get the owner as an active owner member.
    op.execute(
        """
        INSERT INTO community_members (id, community_id, user_id, role, status, joined_at)
        SELECT gen_random_uuid(), id, owner_id, 'owner', 'active', created_at
        FROM communities
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("media_exposure_drops")
    op.drop_table("dead_mans_switch_rules")
    op.drop_table("community_members")
    op.drop_index(op.f("ix_communities_invite_code"), table_name="communities")
    op.drop_column("communities", "invite_code")
    op.drop_column("communities", "require_approval")
    op.drop_column("communities", "visibility")
