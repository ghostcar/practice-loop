"""027_add_media_assets_verification

Revision ID: 1f2f3be8f095
Revises: c4a67950ab23
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1f2f3be8f095"
down_revision: str | None = "c4a67950ab23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_type", sa.String(50), nullable=False),
        sa.Column("owner_ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="staged"),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=False, server_default="application/octet-stream"),
        sa.Column("file_size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sha256_hex", sa.String(64), nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("caption", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_media_assets_owner_type_ref", "media_assets", ["owner_type", "owner_ref_id"])
    op.create_index("ix_media_assets_owner_id_state", "media_assets", ["owner_id", "state"])

    op.create_table(
        "verification_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_type", sa.String(50), nullable=False),
        sa.Column("owner_ref_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hmac", sa.String(64), nullable=False),
        sa.Column("code_length", sa.Integer, nullable=False, server_default="7"),
        sa.Column("state", sa.String(20), nullable=False, server_default="active"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_verification_owner_type_ref", "verification_challenges", ["owner_type", "owner_ref_id"])


def downgrade() -> None:
    op.drop_table("verification_challenges")
    op.drop_table("media_assets")
