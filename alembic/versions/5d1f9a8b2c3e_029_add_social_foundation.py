"""029_add_social_foundation — Platform Social S0 + S1 tables.

Social profiles (alias-based public identity), consent records,
and opaque subject registry for domain adapters.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d1f9a8b2c3e"
down_revision: str | None = "7bf818094186"  # 028_add_tag_numbers
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # social_profiles
    op.create_table(
        "social_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(80), nullable=False),
        sa.Column("alias_normalized", sa.String(80), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("discoverable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("show_in_feed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("alias"),
        sa.UniqueConstraint("alias_normalized"),
    )
    op.create_index("ix_social_profiles_user_id", "social_profiles", ["user_id"], unique=True)
    op.create_index("ix_social_profiles_alias", "social_profiles", ["alias"], unique=True)
    op.create_index("ix_social_profiles_alias_normalized", "social_profiles", ["alias_normalized"], unique=True)

    # social_consents
    op.create_table(
        "social_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consent_version", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ip_address_hash", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "consent_version", name="uq_social_consent_user_version"),
    )
    op.create_index("ix_social_consents_user_id", "social_consents", ["user_id"])

    # social_subjects
    op.create_table(
        "social_subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_type", sa.String(80), nullable=False),
        sa.Column("domain_object_id", sa.String(255), nullable=False),
        sa.Column("projection_snapshot", sa.JSON(), nullable=True),
        sa.Column("projection_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_type", "domain_object_id", name="uq_social_subject_type_object"),
    )
    op.create_index("ix_social_subjects_owner_id", "social_subjects", ["owner_id"])
    op.create_index("ix_social_subjects_subject_type", "social_subjects", ["subject_type"])


def downgrade() -> None:
    op.drop_table("social_subjects")
    op.drop_table("social_consents")
    op.drop_table("social_profiles")
