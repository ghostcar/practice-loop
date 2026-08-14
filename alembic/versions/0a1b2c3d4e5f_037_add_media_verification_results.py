"""037_add_media_verification_results — LLM photo evaluation (Step 7, ADR-075).

Adds:
- media_verification_results (owner_id, media_id FK, verification_type
  code_match|chastity_closed, expected_code_hmac, verdict match|mismatch|unclear,
  confidence 0..100, reasoning, llm_model, consumed_challenge_id, created_at)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0a1b2c3d4e5f"
down_revision: str | None = "f6a7b8c9d0e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_verification_results",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("verification_type", sa.String(50), nullable=False),
        sa.Column("expected_code_hmac", sa.String(64), nullable=True),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reasoning", sa.String(2000), nullable=True),
        sa.Column("llm_model", sa.String(200), nullable=True),
        sa.Column("consumed_challenge_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "verification_type IN ('code_match', 'chastity_closed')",
            name="ck_media_verification_type",
        ),
        sa.CheckConstraint("verdict IN ('match', 'mismatch', 'unclear')", name="ck_media_verdict"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_media_verification_confidence"),
    )
    op.create_index("ix_media_verification_owner_id", "media_verification_results", ["owner_id"])
    op.create_index("ix_media_verification_media_id", "media_verification_results", ["media_id"])


def downgrade() -> None:
    op.drop_index("ix_media_verification_media_id", table_name="media_verification_results")
    op.drop_index("ix_media_verification_owner_id", table_name="media_verification_results")
    op.drop_table("media_verification_results")
