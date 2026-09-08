"""LLM call logs + repair stale portal provider selections (ADR-191).

``llm_call_logs`` records every LLM invocation (success or failure) with
config, model, tokens/cost, latency, status and a truncated error message —
the observability layer the owner asked for (debug «почему LLM не сработал»).

Data repair: selections stored with the legacy portal id suffix
``Omniroute (local)`` (provider names in PORTAL_LLM_PROVIDERS_JSON changed)
no longer match any env provider id, so resolution fell through to None and
every LLM feature silently degraded to «нет активного провайдера». The
migration strips the stale suffix and, when the resulting id does not exist
either, rewrites the selection to the first available portal provider.

Revision ID: 099_llm_call_logs
Revises: 098_substitution_daily_limit
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "099_llm_call_logs"
down_revision: str | None = "098_substitution_daily_limit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_expr() -> str:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return "gen_random_uuid()"
    return "lower(hex(randomblob(16)))"


def upgrade() -> None:
    op.create_table(
        "llm_call_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column(
            "config_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llm_provider_configs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("provider_name", sa.String(100), nullable=True),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("capability", sa.String(20), nullable=False, server_default="text"),
        sa.Column("section", sa.String(50), nullable=True),
        sa.Column("purpose", sa.String(60), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok", index=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )

    # ── Data repair: stale portal ids from an older PORTAL_LLM_PROVIDERS_JSON ──
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    stale = (
        conn.execute(
            sa.text(
                "SELECT DISTINCT portal_provider_id FROM llm_user_selections WHERE portal_provider_id LIKE '% (local)'"
            )
        )
        .scalars()
        .all()
    )
    if not stale:
        return
    import json as _json

    from app.config import settings as _settings

    try:
        raw = _json.loads(_settings.portal_llm_providers_json or "[]")
    except (TypeError, ValueError):
        raw = []
    valid_ids: list[str] = []
    names: list[str] = []
    for i, item in enumerate(raw if isinstance(raw, list) else []):
        if isinstance(item, dict) and str(item.get("name") or "").strip():
            valid_ids.append(f"portal:{i}:{str(item['name']).strip()}")
            names.append(str(item["name"]).strip())
    for old in stale:
        fixed = old.removesuffix(" (local)")
        if fixed not in valid_ids:
            fixed = valid_ids[0] if valid_ids else None
        if fixed is None:
            conn.execute(
                sa.text("DELETE FROM llm_user_selections WHERE portal_provider_id = :old"),
                {"old": old},
            )
        else:
            conn.execute(
                sa.text("UPDATE llm_user_selections SET portal_provider_id = :new WHERE portal_provider_id = :old"),
                {"new": fixed, "old": old},
            )


def downgrade() -> None:
    op.drop_table("llm_call_logs")
