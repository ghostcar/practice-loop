"""Integration tests for Dynamic Subscription Tier Constructor & Promotional Override Engine."""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.monetization import SubscriptionTier, TemporaryFeaturePromotion
from app.models.user import User
from app.tier_guard import check_feature_access, seed_default_tiers_and_grants


@pytest.mark.asyncio
async def test_dynamic_tier_seeding_and_grants(db_session: AsyncSession):
    """Verify seeding of the 5 default subscription tiers and grants."""
    await seed_default_tiers_and_grants(db_session)

    tiers_res = await db_session.execute(select(SubscriptionTier))
    tiers = {t.code: t for t in tiers_res.scalars().all()}

    assert len(tiers) >= 5
    assert "free" in tiers
    assert "standard" in tiers
    assert "pro" in tiers
    assert "ds_master" in tiers
    assert "guild_master" in tiers


@pytest.mark.asyncio
async def test_check_feature_access_when_monetization_disabled(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify check_feature_access opens all features when MONETIZATION_ENABLED is False."""
    settings.monetization_enabled = False
    access = await check_feature_access(db_session, test_user, "ds_portal")
    assert access.allowed is True
    assert access.reason == "monetization_disabled"


@pytest.mark.asyncio
async def test_check_feature_access_admin_and_user_exemption(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify check_feature_access opens all features for admin or monetization exempt users."""
    try:
        settings.monetization_enabled = True
        test_user.is_monetization_exempt = True
        await db_session.flush()

        access = await check_feature_access(db_session, test_user, "community_agent")
        assert access.allowed is True
        assert access.reason == "admin_or_exempt"
    finally:
        settings.monetization_enabled = False


@pytest.mark.asyncio
async def test_temporary_promotional_override(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify active TemporaryFeaturePromotion opens feature code to lower tiers."""
    try:
        settings.monetization_enabled = True
        test_user.is_monetization_exempt = False
        test_user.subscription_tier = "free"

        now = datetime.now()
        promo = TemporaryFeaturePromotion(
            feature_code="ds_portal",
            target_min_tier_code="free",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=7),
            is_active=True,
        )
        db_session.add(promo)
        await db_session.flush()

        access = await check_feature_access(db_session, test_user, "ds_portal")
        assert access.allowed is True
        assert access.reason == "promotional_override"
    finally:
        settings.monetization_enabled = False


@pytest.mark.asyncio
async def test_admin_tiers_constructor_page_access(auth_client: AsyncClient, test_user: User):
    """GET /admin/tiers requires admin role."""
    test_user.role = "admin"
    resp = await auth_client.get("/admin/tiers")
    assert resp.status_code == 200
    assert "Динамический Конструктор Тиров" in resp.text
