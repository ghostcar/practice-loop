"""Create the 17 module tables that exist in models but are missing from the DB.

These tables were added by later feature modules (communities, monetization,
automation, duels, leagues, personas, payments, promo codes, media tokens) but
never had a migration generated, so the live DB is behind the models.

Revision ID: 082_add_missing_module_tables
Revises: 081_social_grant_invariants
"""

from collections.abc import Sequence

from alembic import op
from app.models import Base  # noqa: F401 — imports all modules, registers tables

revision: str = "082_add_missing_module_tables"
down_revision: str | None = "081_social_grant_invariants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Topological order (parents before children) for create_all.
# NOTE: automation_triggers / user_duels / user_league_tiers were removed in
# 094_drop_dead_experimental (ADR-187) — their models no longer exist, so they
# are omitted here to avoid KeyError on fresh bootstrap. Their downgrade drops
# stay below so a full downgrade still removes them.
MISSING_TABLES = [
    "communities",
    "community_member_delegations",
    "community_member_roles",
    "community_posts",
    "community_top_agents",
    "community_tournaments",
    "community_tournament_entries",
    "one_time_media_tokens",
    "payment_invoices",
    "promo_codes",
    "subscription_tiers",
    "temporary_feature_promotions",
    "tier_feature_grants",
    "user_agent_personas",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in MISSING_TABLES]
    # checkfirst=True skips any table that already exists; create_all sorts
    # by FK dependency so children are created after their parents.
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    # Drop children before parents.
    for t in [
        "community_tournament_entries",
        "community_tournaments",
        "user_league_tiers",
        "community_member_delegations",
        "community_member_roles",
        "community_posts",
        "community_top_agents",
        "tier_feature_grants",
        "subscription_tiers",
        "temporary_feature_promotions",
        "promo_codes",
        "user_duels",
        "user_agent_personas",
        "one_time_media_tokens",
        "payment_invoices",
        "automation_triggers",
        "communities",
    ]:
        op.drop_table(t)
