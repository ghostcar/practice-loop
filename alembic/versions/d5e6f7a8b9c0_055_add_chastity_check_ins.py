"""055_add_chastity_check_ins — регулярные чекины ношения (C2 + B3/Q13).

``chastity_check_ins`` — состояние/комфорт/отчёт во время ношения, опционально
с фото-отчётом и LLM-верификацией фото (chastity_closed/code_match). Мягкие
ссылки: session_id → lock_sessions (SET NULL), media_id → media_assets
(SET NULL), verification_result_id → media_verification_results (SET NULL).
Relief-only (PD-013).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"  # 054_add_chastity_device_events
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chastity_check_ins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("lock_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mood", sa.Integer(), nullable=True),
        sa.Column("comfort_level", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("media_id", sa.Uuid(), sa.ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "verification_result_id",
            sa.Uuid(),
            sa.ForeignKey("media_verification_results.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chastity_check_ins_user_id", "chastity_check_ins", ["user_id"])
    op.create_index("ix_chastity_check_ins_session_id", "chastity_check_ins", ["session_id"])
    op.create_index("ix_chastity_check_ins_media_id", "chastity_check_ins", ["media_id"])
    op.create_index("ix_chastity_check_ins_verification_result_id", "chastity_check_ins", ["verification_result_id"])


def downgrade() -> None:
    op.drop_index("ix_chastity_check_ins_verification_result_id", table_name="chastity_check_ins")
    op.drop_index("ix_chastity_check_ins_media_id", table_name="chastity_check_ins")
    op.drop_index("ix_chastity_check_ins_session_id", table_name="chastity_check_ins")
    op.drop_index("ix_chastity_check_ins_user_id", table_name="chastity_check_ins")
    op.drop_table("chastity_check_ins")
