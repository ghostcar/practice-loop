"""Dynamic Security Tier Guard & Feature Access Control Engine."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NamedTuple

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.monetization import SubscriptionTier, TemporaryFeaturePromotion, TierFeatureGrant
from app.models.user import User

logger = logging.getLogger(__name__)


class AccessResult(NamedTuple):
    allowed: bool
    reason: str
    limit_value: int | None = None


DEFAULT_TIERS = [
    {"code": "free", "name": "Бесплатный", "rank": 1, "is_default": True},
    {"code": "standard", "name": "Стандартный", "rank": 2, "is_default": False},
    {"code": "pro", "name": "Персональный ИИ", "rank": 3, "is_default": False},
    {"code": "ds_master", "name": "Ключник D/s", "rank": 4, "is_default": False},
    {"code": "guild_master", "name": "Гильдия", "rank": 5, "is_default": False},
]

DEFAULT_GRANTS = {
    "standard": ["llm_exchange"],
    "pro": ["llm_exchange", "agent_chat", "insights_analytics"],
    "ds_master": ["llm_exchange", "agent_chat", "insights_analytics", "ds_portal"],
    "guild_master": ["llm_exchange", "agent_chat", "insights_analytics", "ds_portal", "community_agent"],
}


async def seed_default_tiers_and_grants(db: AsyncSession) -> None:
    """Seeds default 5 subscription tiers and their initial feature grants if missing."""
    for t in DEFAULT_TIERS:
        existing = (
            await db.execute(select(SubscriptionTier).where(SubscriptionTier.code == t["code"]))
        ).scalar_one_or_none()

        if not existing:
            tier = SubscriptionTier(
                code=t["code"],
                name=t["name"],
                rank=t["rank"],
                is_default=t["is_default"],
            )
            db.add(tier)
            await db.flush()

            feature_codes = DEFAULT_GRANTS.get(t["code"], [])
            for fc in feature_codes:
                grant = TierFeatureGrant(tier_id=tier.id, feature_code=fc)
                db.add(grant)

    await db.flush()


async def check_feature_access(
    db: AsyncSession,
    user: User,
    feature_code: str,
) -> AccessResult:
    """Evaluates dynamic feature permissions, promotions, admin exemptions, and MONETIZATION_ENABLED flag."""
    # 1. Global Monetization Flag Check
    if not getattr(settings, "monetization_enabled", False):
        return AccessResult(allowed=True, reason="monetization_disabled")

    # 2. Admin & User Exemption Check
    if user.role == "admin" or user.is_monetization_exempt:
        return AccessResult(allowed=True, reason="admin_or_exempt")

    now = datetime.now()

    # 3. Temporary Promotional Override Check
    promo_res = await db.execute(
        select(TemporaryFeaturePromotion).where(
            TemporaryFeaturePromotion.feature_code == feature_code,
            TemporaryFeaturePromotion.is_active.is_(True),
            TemporaryFeaturePromotion.starts_at <= now,
            TemporaryFeaturePromotion.ends_at >= now,
        )
    )
    promos = promo_res.scalars().all()
    if promos:
        return AccessResult(allowed=True, reason="promotional_override")

    # 4. Dynamic Tier Grant Check
    user_tier_code = user.subscription_tier or "free"
    tier_res = await db.execute(select(SubscriptionTier).where(SubscriptionTier.code == user_tier_code))
    user_tier = tier_res.scalar_one_or_none()

    if not user_tier:
        return AccessResult(allowed=False, reason="tier_not_found")

    grant_res = await db.execute(
        select(TierFeatureGrant).where(
            TierFeatureGrant.tier_id == user_tier.id,
            TierFeatureGrant.feature_code == feature_code,
        )
    )
    grant = grant_res.scalar_one_or_none()

    if grant:
        return AccessResult(allowed=True, reason="tier_grant", limit_value=grant.limit_value)

    return AccessResult(allowed=False, reason="feature_not_granted_for_tier")


def require_feature(feature_code: str):
    """FastAPI Dependency enforcing feature code access."""

    async def _dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        access = await check_feature_access(db, user, feature_code)
        if not access.allowed:
            raise HTTPException(
                status_code=402,
                detail=f"Доступ к модулю '{feature_code}' требует повышения тира подписки.",
            )
        return access

    return _dependency
