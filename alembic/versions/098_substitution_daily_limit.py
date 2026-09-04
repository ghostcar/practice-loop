"""Medication substitution & daily-limit confirmation (ADR-190, phases F/G).

- med_intakes.substituted_for_id: FK medications — приём выполнен заменителем
  (medication_id = фактический препарат; substituted_for_id = тот, вместо
  которого принят); автотекст в notes.
- med_intakes.ul_confirmed: явное подтверждение превышения суточной дозы
  (кнопка «Принять с превышением», ADR-190 §8).

Revision ID: 098_substitution_daily_limit
Revises: 097_substances_components
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "098_substitution_daily_limit"
down_revision: str | None = "097_substances_components"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "med_intakes",
        sa.Column(
            "substituted_for_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medications.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_med_intakes_substituted_for_id", "med_intakes", ["substituted_for_id"])
    op.add_column(
        "med_intakes",
        sa.Column(
            "ul_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("med_intakes", "ul_confirmed")
    op.drop_index("ix_med_intakes_substituted_for_id", table_name="med_intakes")
    op.drop_column("med_intakes", "substituted_for_id")
