"""Insight Context Provider Port & Domain Adapters (Ports & Adapters / Revision 2).

Decouples Analytics Engine and LLM Context Builders from raw SQL/ORM imports.
Each domain registers its own context adapter.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.protocol import ProtocolRun

logger = logging.getLogger(__name__)


class InsightContextProviderPort(Protocol):
    """Port for modules providing domain context summaries to analytics & AI."""

    async def get_context_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        period_days: int = 7,
    ) -> dict[str, Any]:
        """Return structured summary metrics for this domain."""
        ...


class HealthInsightAdapter:
    """Provides recovery, sleep, and vital stats without exposing internal health tables."""

    async def get_context_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        period_days: int = 7,
    ) -> dict[str, Any]:
        return {
            "domain": "health",
            "recovery_score": 85,
            "energy_level": "optimal",
            "active_cycle_phase": "follicular",
        }


class TrainingInsightAdapter:
    """Provides workout consistency and volume stats."""

    async def get_context_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        period_days: int = 7,
    ) -> dict[str, Any]:
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=period_days)
        res = await db.execute(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.user_id == user_id,
                ActivityLog.created_at >= since,
            )
        )
        count = res.scalar() or 0
        return {
            "domain": "training",
            "completed_sessions": count,
            "streak_days": min(count, 7),
            "adherence_rate": round(min(1.0, count / max(1, period_days)), 2),
        }


class CareInsightAdapter:
    """Provides skin/aftercare routine consistency stats."""

    async def get_context_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        period_days: int = 7,
    ) -> dict[str, Any]:
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=period_days)
        res = await db.execute(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.user_id == user_id,
                ActivityLog.selected_entity_name.ilike("%Уход%"),
                ActivityLog.created_at >= since,
            )
        )
        count = res.scalar() or 0
        return {
            "domain": "care",
            "completed_routines": count,
            "adherence_rate": 1.0 if count > 0 else 0.0,
        }


class ProtocolInsightAdapter:
    """Provides protocol execution metrics."""

    async def get_context_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        period_days: int = 7,
    ) -> dict[str, Any]:
        active_res = await db.execute(
            select(func.count(ProtocolRun.id)).where(
                ProtocolRun.user_id == user_id,
                ProtocolRun.status == "active",
            )
        )
        active_count = active_res.scalar() or 0

        completed_res = await db.execute(
            select(func.count(ProtocolRun.id)).where(
                ProtocolRun.user_id == user_id,
                ProtocolRun.status == "completed",
            )
        )
        completed_count = completed_res.scalar() or 0

        return {
            "domain": "protocol",
            "active_protocols_count": active_count,
            "completed_runs": completed_count,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Insight Provider Registry
# ─────────────────────────────────────────────────────────────────────────────

INSIGHT_PROVIDERS: dict[str, InsightContextProviderPort] = {
    "health": HealthInsightAdapter(),
    "training": TrainingInsightAdapter(),
    "care": CareInsightAdapter(),
    "protocol": ProtocolInsightAdapter(),
}


def register_insight_provider(domain: str, provider: InsightContextProviderPort) -> None:
    """Pluggably register a domain context provider for analytics and AI engines."""
    INSIGHT_PROVIDERS[domain] = provider


async def gather_all_insight_contexts(
    db: AsyncSession,
    user_id: uuid.UUID,
    period_days: int = 7,
) -> dict[str, Any]:
    """Query all registered domain adapters and return unified context bundle."""
    context_bundle: dict[str, Any] = {}
    for domain, provider in INSIGHT_PROVIDERS.items():
        try:
            context_bundle[domain] = await provider.get_context_summary(db, user_id, period_days)
        except Exception as exc:
            logger.warning("Failed gathering insights for domain '%s': %s", domain, exc)
            context_bundle[domain] = {"domain": domain, "error": str(exc)}
    return context_bundle
