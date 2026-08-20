"""Integration tests for User Billing Showcase & Multi-Gateway Payment Engine."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.gateways import create_payment_checkout_session, process_payment_webhook
from app.models.user import User


@pytest.mark.asyncio
async def test_billing_showcase_page_rendering(auth_client: AsyncClient):
    """GET /billing returns 200 OK for authenticated user."""
    resp = await auth_client.get("/billing")
    assert resp.status_code == 200
    assert "Доступные Тиры Подписки" in resp.text


@pytest.mark.asyncio
async def test_create_payment_checkout_session_all_gateways(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify session creation across Stripe, Telegram Stars, Crypto, and ЮKassa."""
    for gateway in ["stripe", "telegram_stars", "crypto", "yukassa"]:
        session_info = await create_payment_checkout_session(db_session, test_user, tier_code="pro", gateway=gateway)
        assert session_info["status"] == "success"
        assert session_info["gateway"] == gateway
        assert "checkout_url" in session_info


@pytest.mark.asyncio
async def test_payment_webhook_upgrades_user_subscription(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify webhook processing marks invoice paid and upgrades user.subscription_tier."""
    session_info = await create_payment_checkout_session(db_session, test_user, tier_code="ds_master", gateway="stripe")
    ext_id = session_info["external_invoice_id"]

    webhook_payload = {"external_invoice_id": ext_id, "event": "payment_intent.succeeded"}
    result = await process_payment_webhook(db_session, gateway="stripe", payload=webhook_payload)

    assert result["status"] == "success"
    assert result["upgraded_tier"] == "ds_master"

    # Verify user record in DB
    user_res = await db_session.execute(select(User).where(User.id == test_user.id))
    updated_user = user_res.scalar_one()
    assert updated_user.subscription_tier == "ds_master"
