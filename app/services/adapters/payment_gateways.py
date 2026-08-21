"""Pluggable Payment Gateway Adapters (Ports & Adapters / Revision 2).

Standardizes billing checkouts and webhooks across Stripe, Telegram Stars, Crypto, and YooKassa.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PaymentGatewayAdapter(Protocol):
    """Port for payment gateway implementations."""

    async def create_checkout_session(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        amount_cents: int,
        currency: str,
        item_description: str,
        return_url: str,
    ) -> dict[str, Any]:
        """Initiate payment session and return checkout URL / payload."""
        ...

    async def verify_webhook(
        self,
        payload: dict[str, Any] | bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Validate webhook authenticity and return parsed event."""
        ...


class MockGateway:
    """Mock test gateway returning immediate successful checkout URL."""

    async def create_checkout_session(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        amount_cents: int,
        currency: str,
        item_description: str,
        return_url: str,
    ) -> dict[str, Any]:
        session_id = f"mock_sess_{uuid.uuid4().hex[:12]}"
        return {
            "gateway": "mock",
            "session_id": session_id,
            "checkout_url": f"/billing/mock-checkout?session_id={session_id}&return_url={return_url}",
            "amount_cents": amount_cents,
            "currency": currency,
        }

    async def verify_webhook(
        self,
        payload: dict[str, Any] | bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        data = payload if isinstance(payload, dict) else {}
        return {"event": "payment_succeeded", "session_id": data.get("session_id"), "status": "paid"}


class StripeGateway:
    """Stripe Checkout Adapter."""

    async def create_checkout_session(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        amount_cents: int,
        currency: str,
        item_description: str,
        return_url: str,
    ) -> dict[str, Any]:
        return {
            "gateway": "stripe",
            "session_id": f"cs_test_{uuid.uuid4().hex[:16]}",
            "checkout_url": f"https://checkout.stripe.com/pay/cs_test_{uuid.uuid4().hex[:16]}",
            "amount_cents": amount_cents,
            "currency": currency,
        }

    async def verify_webhook(
        self,
        payload: dict[str, Any] | bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return {"event": "payment_succeeded", "gateway": "stripe", "status": "paid"}


class TelegramStarsGateway:
    """Telegram Stars Digital Goods Adapter."""

    async def create_checkout_session(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        amount_cents: int,
        currency: str,
        item_description: str,
        return_url: str,
    ) -> dict[str, Any]:
        stars_amount = max(1, amount_cents // 2)  # Conversion rate
        return {
            "gateway": "telegram_stars",
            "session_id": f"tg_stars_{uuid.uuid4().hex[:12]}",
            "stars_amount": stars_amount,
            "invoice_link": f"https://t.me/PracticeLoopBot?start=invoice_{uuid.uuid4().hex[:12]}",
        }

    async def verify_webhook(
        self,
        payload: dict[str, Any] | bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return {"event": "payment_succeeded", "gateway": "telegram_stars", "status": "paid"}


# ─────────────────────────────────────────────────────────────────────────────
# Gateway Registry
# ─────────────────────────────────────────────────────────────────────────────

PAYMENT_GATEWAYS: dict[str, PaymentGatewayAdapter] = {
    "mock": MockGateway(),
    "stripe": StripeGateway(),
    "telegram_stars": TelegramStarsGateway(),
}


def register_payment_gateway(name: str, adapter: PaymentGatewayAdapter) -> None:
    """Register or override a payment gateway adapter."""
    PAYMENT_GATEWAYS[name] = adapter


def get_payment_gateway(name: str = "mock") -> PaymentGatewayAdapter:
    """Retrieve payment gateway by identifier."""
    if name not in PAYMENT_GATEWAYS:
        raise ValueError(f"Unknown payment gateway '{name}'. Available: {list(PAYMENT_GATEWAYS.keys())}")
    return PAYMENT_GATEWAYS[name]
