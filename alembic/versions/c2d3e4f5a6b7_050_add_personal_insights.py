"""050_add_personal_insights — Personal Insights (Шаг 17, ADR-093).

Явно запрошенный кросс-модульный LLM-анализ личных данных (PRODUCT_OVERVIEW §12):

- ``insight_runs``    — запуск анализа: period_start/period_end, sections (JSON),
  status (completed/failed), summary, usage_tokens/usage_cost, error;
- ``insight_findings``— находки анализа (run_id FK CASCADE): section, title,
  summary, used_data (JSON — какие данные использованы).

Relief-only (PD-013): без игровой интеграции. Все записи Private Record.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"  # 049_add_care_products
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "insight_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("usage_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usage_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insight_runs_user_id", "insight_runs", ["user_id"])
    op.create_index("ix_insight_runs_period_start", "insight_runs", ["period_start"])
    op.create_index("ix_insight_runs_period_end", "insight_runs", ["period_end"])

    op.create_table(
        "insight_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("insight_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("used_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insight_findings_run_id", "insight_findings", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_insight_findings_run_id", table_name="insight_findings")
    op.drop_table("insight_findings")
    op.drop_index("ix_insight_runs_period_end", table_name="insight_runs")
    op.drop_index("ix_insight_runs_period_start", table_name="insight_runs")
    op.drop_index("ix_insight_runs_user_id", table_name="insight_runs")
    op.drop_table("insight_runs")
