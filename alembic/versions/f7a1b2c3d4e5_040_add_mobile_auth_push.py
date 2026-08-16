"""040_add_mobile_auth_push — Mobile Foundation (M4): bearer-auth + push devices.

Adds:
- ``api_tokens``   — revocable, rotating refresh tokens for the JSON auth API
- ``push_devices`` — device tokens registered for push notifications
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a1b2c3d4e5"
down_revision: str | None = "a5f6e7d8c9b0"  # 039_add_user_prefs
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # api_tokens — refresh tokens (opaque, stored as SHA-256 hash)
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("client_name", sa.String(100), nullable=True),
        sa.Column("platform", sa.String(30), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_from_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_api_token_hash"),
    )
    op.create_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])
    op.create_index("ix_api_tokens_token_hash", "api_tokens", ["token_hash"], unique=True)

    # push_devices — registered push notification devices
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("device_token", sa.String(512), nullable=False),
        sa.Column("app_version", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "platform", "device_token", name="uq_push_device_token"),
    )
    op.create_index("ix_push_devices_user_id", "push_devices", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_devices_user_id", table_name="push_devices")
    op.drop_table("push_devices")
    op.drop_index("ix_api_tokens_token_hash", table_name="api_tokens")
    op.drop_index("ix_api_tokens_user_id", table_name="api_tokens")
    op.drop_table("api_tokens")
