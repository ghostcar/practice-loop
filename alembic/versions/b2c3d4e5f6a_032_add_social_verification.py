"""032_add_social_verification — Platform Social S4: verification, comments, encouragements.

Frozen verification policies, request state machine (open→verified/review_required/failed),
one-vote-per-verifier, plain text comments, lightweight encouragements.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a"
down_revision: str | None = "a1b2c3d4e5f"  # 031_add_social_publications
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # social_verification_policies
    op.create_table(
        "social_verification_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("verifier_scope", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("min_approvals", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_rejections", sa.Integer(), nullable=True),
        sa.Column("deadline_hours", sa.Integer(), nullable=False, server_default=sa.text("72")),
        sa.Column("no_quorum_action", sa.String(20), nullable=False, server_default=sa.text("'review_required'")),
        sa.Column("require_reject_comment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_policies_owner", "social_verification_policies", ["owner_id"])

    # social_verification_requests
    op.create_table(
        "social_verification_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "policy_id",
            sa.Uuid(),
            sa.ForeignKey("social_verification_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_id", sa.Uuid(), sa.ForeignKey("social_subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requester_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("approvals", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rejections", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_requests_subject", "social_verification_requests", ["subject_id"])
    op.create_index("ix_verification_requests_requester", "social_verification_requests", ["requester_id"])

    # social_verification_votes
    op.create_table(
        "social_verification_votes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "request_id",
            sa.Uuid(),
            sa.ForeignKey("social_verification_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("voter_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.String(10), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "voter_id", name="uq_verification_vote"),
    )
    op.create_index("ix_verification_votes_request", "social_verification_votes", ["request_id"])
    op.create_index("ix_verification_votes_voter", "social_verification_votes", ["voter_id"])

    # social_comments
    op.create_table(
        "social_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_edited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_comments_author", "social_comments", ["author_id"])
    op.create_index("ix_social_comments_target", "social_comments", ["target_type", "target_id"])

    # social_encouragements
    op.create_table(
        "social_encouragements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("encouragement_type", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sender_id", "target_type", "target_id", name="uq_encouragement_once"),
    )
    op.create_index("ix_social_encouragements_sender", "social_encouragements", ["sender_id"])


def downgrade() -> None:
    op.drop_table("social_encouragements")
    op.drop_table("social_comments")
    op.drop_table("social_verification_votes")
    op.drop_table("social_verification_requests")
    op.drop_table("social_verification_policies")
