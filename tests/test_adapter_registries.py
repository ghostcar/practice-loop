import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.adapters.insights import (
    gather_all_insight_contexts,
    register_insight_provider,
)
from app.services.adapters.notifications import (
    dispatch_notification,
    register_notification_channel,
)
from app.services.adapters.payment_gateways import (
    get_payment_gateway,
    register_payment_gateway,
)


@pytest.mark.asyncio
async def test_payment_gateway_registry(db_session: AsyncSession, test_user: User):
    # 1. Standard mock gateway
    gw = get_payment_gateway("mock")
    session = await gw.create_checkout_session(
        db=db_session,
        user_id=test_user.id,
        amount_cents=1990,
        currency="RUB",
        item_description="Subscription",
        return_url="/billing/success",
    )
    assert session["gateway"] == "mock"
    assert "mock_sess_" in session["session_id"]

    # 2. Custom gateway registration
    class CustomCryptoGateway:
        async def create_checkout_session(self, db, user_id, amount_cents, currency, item_description, return_url):
            return {"gateway": "custom_crypto", "pay_address": "0x123456789"}

        async def verify_webhook(self, payload, headers):
            return {"status": "confirmed"}

    register_payment_gateway("custom_crypto", CustomCryptoGateway())
    custom_gw = get_payment_gateway("custom_crypto")
    custom_sess = await custom_gw.create_checkout_session(db_session, test_user.id, 5000, "USDT", "Plan", "/done")
    assert custom_sess["gateway"] == "custom_crypto"


@pytest.mark.asyncio
async def test_notification_dispatcher(db_session: AsyncSession, test_user: User):
    # 1. Default channels (in_app only for user without linked telegram)
    res = await dispatch_notification(
        db=db_session,
        user_id=test_user.id,
        event_type="dms_warning",
        title="Предупреждение DMS",
        message="Осталось 2 часа до контрольного чекина",
    )
    assert res.get("in_app") is True
    # User has no linked telegram → telegram not in default channels
    assert "telegram" not in res

    # 2. Explicitly request telegram (will return False — no linked chat)
    tg_res = await dispatch_notification(
        db=db_session,
        user_id=test_user.id,
        event_type="dms_warning",
        title="TG Test",
        message="Explicit telegram channel",
        channels=["in_app", "telegram"],
    )
    assert tg_res["in_app"] is True
    assert tg_res["telegram"] is False  # no linked chat

    # 3. Register custom channel
    class CustomPushChannel:
        async def send(self, db, user_id, event_type, title, message, payload=None):
            return True

    register_notification_channel("custom_v2", CustomPushChannel())
    push_res = await dispatch_notification(
        db=db_session,
        user_id=test_user.id,
        event_type="test",
        title="Push test",
        message="Push message",
        channels=["custom_v2"],
    )
    assert push_res["custom_v2"] is True


@pytest.mark.asyncio
async def test_insight_provider_registry(db_session: AsyncSession, test_user: User):
    # 1. Gather default insights
    insights = await gather_all_insight_contexts(db=db_session, user_id=test_user.id, period_days=7)
    assert "health" in insights
    assert "training" in insights
    assert "care" in insights
    assert "protocol" in insights
    assert insights["health"]["recovery_score"] == 85

    # 2. Register a new domain (e.g. breathplay / biofeedback)
    class BreathplayInsightAdapter:
        async def get_context_summary(self, db, user_id, period_days=7):
            return {"domain": "breathplay", "avg_retention_sec": 45, "sessions": 3}

    register_insight_provider("breathplay", BreathplayInsightAdapter())
    updated_insights = await gather_all_insight_contexts(db=db_session, user_id=test_user.id)
    assert "breathplay" in updated_insights
    assert updated_insights["breathplay"]["avg_retention_sec"] == 45
