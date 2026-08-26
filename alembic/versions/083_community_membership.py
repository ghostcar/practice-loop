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
from sqlalchemy import inspect

from alembic import op
from app.models import Base  # noqa: F401 — imports all modules, registers tables

revision: str = "083_community_membership"
down_revision: str | None = "082_add_missing_module_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that exist in models but not yet in the DB.
# `communities` itself never received a migration — it was created by
# create_all() in dev environments. On a fresh database (CI, new deploys)
# it must be created BEFORE the column adds / FK creation below.
MISSING_TABLES = [
    "communities",
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


def _has_index(conn, index_name: str) -> bool:
    res = conn.execute(sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :i"), {"i": index_name})
    return res.scalar_one_or_none() is not None


def _has_table(conn, name: str) -> bool:
    return name in inspect(conn).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create missing tables from the live model metadata first
    #    (FK-sorted, idempotent). On an existing dev DB nothing happens;
    #    on a fresh DB this creates `communities` with all current columns,
    #    so the _has_column() adds below are skipped naturally.
    with op.get_context().autocommit_block():
        tables = [Base.metadata.tables[name] for name in MISSING_TABLES if name in Base.metadata.tables]
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    # 2. Idempotent column adds (no-ops when the table came from metadata).
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
    # NOTE: never rollback() inside a migration — on a fresh DB the index already
    # exists (created from model metadata), and bind.rollback() poisons alembic's
    # transaction so every later migration applies DDL but loses its version bump.
    if not _has_index(bind, "ix_communities_invite_code"):
        op.create_index(op.f("ix_communities_invite_code"), "communities", ["invite_code"], unique=False)

    # 3. Backfill: existing communities get the owner as an active owner member.
    op.execute(
        """
        INSERT INTO community_members (id, community_id, user_id, role, status, joined_at)
        SELECT gen_random_uuid(), id, owner_id, 'owner', 'active', created_at
        FROM communities
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Idempotent drops: on a fresh DB these tables were created by BOTH this
    # migration (from metadata) and 084, so they may already be gone when the
    # reverse chain reaches this revision. `communities` itself is left in place
    # when it was created here from metadata (no owning revision to drop it).
    for t in ("media_exposure_drops", "dead_mans_switch_rules", "community_members"):
        if _has_table(bind, t):
            op.drop_table(t)
    if _has_index(bind, "ix_communities_invite_code"):
        op.drop_index(op.f("ix_communities_invite_code"), table_name="communities")
    if _has_column(bind, "communities", "invite_code"):
        op.drop_column("communities", "invite_code")
    if _has_column(bind, "communities", "require_approval"):
        op.drop_column("communities", "require_approval")
    if _has_column(bind, "communities", "visibility"):
        op.drop_column("communities", "visibility")
