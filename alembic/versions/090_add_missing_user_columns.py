"""Add users columns present in the ORM model but missing from migrations.

The User model grew subscription_tier and is_monetization_exempt without a
migration (they existed only via dev create_all()). On a fresh database (CI
e2e, new deploys) any SELECT on users fails with UndefinedColumnError.

NOT owned here (already migrated): timezone/timezone_confirmed_at (024),
health_adaptation_* (070), pin_hash (089).

Revision ID: 090_add_missing_user_columns
Revises: 071_social_pub_source
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "090_add_missing_user_columns"
down_revision: str | None = "071_social_pub_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(conn, table: str, column: str) -> bool:
    res = conn.execute(
        sa.text("SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
        {"t": table, "c": column},
    )
    return res.scalar_one_or_none() is not None


def upgrade() -> None:
    bind = op.get_bind()
    # NOT NULL columns get a server_default so the ALTER works on existing rows
    # (the ORM keeps its Python-side defaults; server_default is harmless).
    adds = [
        ("subscription_tier", sa.String(50), sa.text("'free'"), False),
        ("is_monetization_exempt", sa.Boolean(), sa.text("false"), False),
    ]
    for name, type_, server_default, nullable in adds:
        if not _has_column(bind, "users", name):
            op.add_column(
                "users",
                sa.Column(name, type_, server_default=server_default, nullable=nullable),
            )


def downgrade() -> None:
    for name in ("is_monetization_exempt", "subscription_tier"):
        op.drop_column("users", name)
