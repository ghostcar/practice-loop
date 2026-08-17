"""Auto-run Personal Insights (ADR-095).

Run a cross-module insights analysis for users who opted in via
``prefs.insights_auto``. Mirrors the training auto-analysis pattern: picks an
active LLM config, runs ``analyze_insights`` over the configured lookback
window, persists ``insight_runs``/``insight_findings``.

Relief-only (PD-013): no points/penalties.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insights import INSIGHT_SECTIONS, InsightFinding, InsightRun
from app.models.llm_config import LLMProviderConfig
from app.models.user import User
from app.prefs import prefs_from_dict

logger = logging.getLogger(__name__)


async def run_auto_insights(db: AsyncSession) -> int:
    """Run insights for users with ``insights_auto`` enabled. Returns run count."""
    users = (await db.execute(select(User))).scalars().all()
    runs = 0
    for user in users:
        prefs = prefs_from_dict(user.prefs)
        if not prefs.insights_auto:
            continue
        config = (
            await db.execute(
                select(LLMProviderConfig).where(
                    LLMProviderConfig.user_id == user.id,
                    LLMProviderConfig.is_active.is_(True),
                )
            )
        ).scalars().first()
        if config is None:
            continue
        try:
            from app.llm.pipeline import analyze_insights

            days = prefs.insights_auto_days
            end = date.today()
            start = end - timedelta(days=days)
            run = InsightRun(
                user_id=user.id,
                period_start=start,
                period_end=end,
                sections=list(INSIGHT_SECTIONS),
                status="completed",
            )
            db.add(run)
            await db.flush()

            result = await analyze_insights(
                db=db,
                user_id=user.id,
                llm_config=config,
                sections=list(INSIGHT_SECTIONS),
                period_start=start,
                period_end=end,
                locale=user.locale or "en",
                llm_mode=prefs.llm_mode,
            )
            run.summary = result.get("summary") or None
            run.usage_tokens = result.get("_usage", {}).get("total_tokens", 0)
            run.usage_cost = result.get("_usage", {}).get("cost", 0.0)
            run.completed_at = _now_utc()
            for finding in result.get("findings", []):
                db.add(
                    InsightFinding(
                        run_id=run.id,
                        section=finding["section"],
                        title=finding["title"],
                        summary=finding["summary"],
                        used_data=finding.get("used_data") or [],
                    )
                )
            runs += 1
        except Exception:
            logger.exception("auto-insights failed for user %s", user.id)
            await db.rollback()
            continue
    if runs:
        await db.commit()
    return runs


def _now_utc():
    from datetime import UTC, datetime

    return datetime.now(UTC)
