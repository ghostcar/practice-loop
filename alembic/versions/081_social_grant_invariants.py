"""Add delegation expiry and concurrency invariants.

Revision ID: 081_social_grant_invariants
Revises: 080_managed_sub_telegram
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "081_social_grant_invariants"
down_revision: str | None = "080_managed_sub_telegram"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE activity_sessions SET status = 'ended' WHERE status IN ('completed', 'interrupted')")
    op.create_check_constraint(
        "ck_activity_session_status", "activity_sessions", "status IN ('created', 'active', 'ended')"
    )
    op.create_check_constraint("ck_adaptive_program_total_days", "adaptive_programs", "total_days BETWEEN 1 AND 365")
    op.create_check_constraint(
        "ck_adaptive_program_current_day", "adaptive_programs", "current_day BETWEEN 1 AND total_days"
    )
    op.create_check_constraint(
        "ck_adaptive_program_difficulty", "adaptive_programs", "difficulty_level BETWEEN 1 AND 5"
    )
    op.create_check_constraint(
        "ck_adaptive_program_status", "adaptive_programs", "status IN ('active', 'paused', 'completed')"
    )
    op.create_unique_constraint("uq_adaptive_step_program_day", "adaptive_program_steps", ["program_id", "day_number"])
    op.create_check_constraint("ck_adaptive_step_day_number", "adaptive_program_steps", "day_number >= 1")
    op.create_check_constraint(
        "ck_adaptive_step_status",
        "adaptive_program_steps",
        "status IN ('pending', 'completed', 'adapted', 'skipped')",
    )
    op.add_column("capability_grants", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE capability_grants SET expires_at = created_at + interval '24 hours' WHERE expires_at IS NULL")
    op.alter_column("capability_grants", "expires_at", nullable=False)
    op.create_check_constraint(
        "ck_capability_grant_status",
        "capability_grants",
        "status IN ('pending', 'active', 'paused', 'revoked')",
    )
    op.create_check_constraint(
        "ck_capability_grant_expiry",
        "capability_grants",
        "expires_at > created_at",
    )
    op.create_unique_constraint(
        "uq_managed_sub_registered_pair",
        "managed_submissives",
        ["top_user_id", "sub_user_id"],
    )
    op.create_index(
        "uq_capability_grant_active_pair",
        "capability_grants",
        ["top_user_id", "sub_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND top_user_id IS NOT NULL"),
    )
    op.create_table(
        "capability_grant_claim_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invite_code_hash", sa.String(length=64), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_capability_grant_claim_attempts_actor_id", "capability_grant_claim_attempts", ["actor_id"])
    op.create_index("ix_capability_grant_claim_attempts_created_at", "capability_grant_claim_attempts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_capability_grant_claim_attempts_created_at", table_name="capability_grant_claim_attempts")
    op.drop_index("ix_capability_grant_claim_attempts_actor_id", table_name="capability_grant_claim_attempts")
    op.drop_table("capability_grant_claim_attempts")
    op.drop_index("uq_capability_grant_active_pair", table_name="capability_grants")
    op.drop_constraint("uq_managed_sub_registered_pair", "managed_submissives", type_="unique")
    op.drop_constraint("ck_capability_grant_expiry", "capability_grants", type_="check")
    op.drop_constraint("ck_capability_grant_status", "capability_grants", type_="check")
    op.drop_column("capability_grants", "expires_at")
    op.drop_constraint("ck_adaptive_step_status", "adaptive_program_steps", type_="check")
    op.drop_constraint("ck_adaptive_step_day_number", "adaptive_program_steps", type_="check")
    op.drop_constraint("uq_adaptive_step_program_day", "adaptive_program_steps", type_="unique")
    op.drop_constraint("ck_adaptive_program_status", "adaptive_programs", type_="check")
    op.drop_constraint("ck_adaptive_program_difficulty", "adaptive_programs", type_="check")
    op.drop_constraint("ck_adaptive_program_current_day", "adaptive_programs", type_="check")
    op.drop_constraint("ck_adaptive_program_total_days", "adaptive_programs", type_="check")
    op.drop_constraint("ck_activity_session_status", "activity_sessions", type_="check")
