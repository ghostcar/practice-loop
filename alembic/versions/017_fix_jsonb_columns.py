"""Fix JSON columns created as Text in migration 006.

Migration 006 created `entities.gamification_config` and `points_profiles.config`
as `sa.Text()`, while the ORM models declare `JSON` and the seed scripts pass
Python dicts. On a clean PostgreSQL schema those inserts fail
(`can't adapt type 'dict'`), so seeds crash. `points_transactions.meta` was
already fixed in migration 014; these two were missed.

Revision ID: 017
Revises: 016_add_store_raw_response
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # entities.gamification_config: Text → JSONB (migration 006 created Text)
    op.alter_column(
        "entities",
        "gamification_config",
        type_=postgresql.JSONB,
        postgresql_using="gamification_config::jsonb",
    )

    # points_profiles.config: Text → JSONB (migration 006 created Text with text default)
    # Drop the text default first — Postgres cannot auto-cast `'{}'` default to jsonb.
    op.alter_column("points_profiles", "config", server_default=None)
    op.alter_column(
        "points_profiles",
        "config",
        type_=postgresql.JSONB,
        postgresql_using="config::jsonb",
        server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    op.alter_column(
        "points_profiles",
        "config",
        type_=sa.Text(),
        postgresql_using="config::text",
        server_default=sa.text("'{}'"),
    )
    op.alter_column(
        "entities",
        "gamification_config",
        type_=sa.Text(),
        postgresql_using="gamification_config::text",
    )
