"""Add Telegram linking fields to ManagedSubmissive (Step 74 / ADR-130).

Revision ID: 080_managed_sub_telegram
Revises: 079_wear_check_ins
Create Date: 2026-08-20 03:28:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "080_managed_sub_telegram"
down_revision: Union[str, None] = "079_wear_check_ins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("managed_submissives", sa.Column("telegram_chat_id", sa.String(length=64), nullable=True))
    op.add_column("managed_submissives", sa.Column("telegram_link_code", sa.String(length=32), nullable=True))
    op.add_column("managed_submissives", sa.Column("telegram_link_code_expires", sa.DateTime(timezone=True), nullable=True))

    op.create_index(op.f("ix_managed_submissives_telegram_chat_id"), "managed_submissives", ["telegram_chat_id"], unique=False)
    op.create_index(op.f("ix_managed_submissives_telegram_link_code"), "managed_submissives", ["telegram_link_code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_managed_submissives_telegram_link_code"), table_name="managed_submissives")
    op.drop_index(op.f("ix_managed_submissives_telegram_chat_id"), table_name="managed_submissives")

    op.drop_column("managed_submissives", "telegram_link_code_expires")
    op.drop_column("managed_submissives", "telegram_link_code")
    op.drop_column("managed_submissives", "telegram_chat_id")
