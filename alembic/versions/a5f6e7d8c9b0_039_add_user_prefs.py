"""039_add_user_prefs — user preferences JSONB (Step 9e, DESIGN_V2 §16).

Adds ``users.prefs`` — a JSONB blob holding customization/discretion state:
accent set, list density, dashboard block order/visibility, discretion mode
(off/always/schedule) with a daily window, sensitive-image blur level and the
raw theme choice (dark/light/system).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a5f6e7d8c9b0"
down_revision: str | None = "1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "prefs",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "prefs")
