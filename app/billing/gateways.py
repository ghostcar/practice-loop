"""Multi-Gateway Payment Dispatcher & Webhook Processor Engine."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import PaymentInvoice
from app.models.user import User

logger = logging.getLogger(__name__)

PRICES_MAP = {
    "standard": {"amount": 9.99, "currency": "USD"},
    "pro": {"amount": 19.99, "currency": "USD"},
    "ds_master": {"amount": 29.99, "currency": "USD"},
    "guild_master": {"amount": 49.99, "currency": "USD"},
}


async def create_payment_checkout_session(
    db: AsyncSession,
    user: User,
    tier_code: str,
    gateway: str = "stripe",
) -> dict[str, str | float]:
    """Generates a payment invoice and checkout URL for chosen gateway."""
    price_info = PRICES_MAP.get(tier_code, {"amount": 9.99, "currency": "USD"})
    external_invoice_id = f"inv_{gateway}_{uuid.uuid4().hex[:12]}"

    invoice = PaymentInvoice(
        user_id=user.id,
        tier_code=tier_code,
        gateway=gateway,
        external_invoice_id=external_invoice_id,
        amount=price_info["amount"],
        currency=price_info["currency"],
        status="pending",
    )
    db.add(invoice)
    await db.flush()

    checkout_url = f"/billing/checkout-redirect?inv={external_invoice_id}&gateway={gateway}"
    if gateway == "stripe":
        checkout_url = f"https://checkout.stripe.com/pay/{external_invoice_id}"
    elif gateway == "telegram_stars":
        checkout_url = f"tg://invoice?code={external_invoice_id}"
    elif gateway == "crypto":
        checkout_url = f"https://nowpayments.io/payment/?iid={external_invoice_id}"
    elif gateway == "yukassa":
        checkout_url = f"https://yoomoney.ru/checkout/{external_invoice_id}"

    return {
        "status": "success",
        "invoice_id": str(invoice.id),
        "external_invoice_id": external_invoice_id,
        "checkout_url": checkout_url,
        "amount": invoice.amount,
        "currency": invoice.currency,
        "gateway": gateway,
    }


async def process_payment_webhook(
    db: AsyncSession,
    gateway: str,
    payload: dict,
) -> dict[str, str]:
    """Processes payment webhook notification and updates user subscription tier."""
    external_id = payload.get("external_invoice_id") or payload.get("id")
    if not external_id:
        return {"status": "ignored", "reason": "missing_external_invoice_id"}

    invoice = (
        await db.execute(select(PaymentInvoice).where(PaymentInvoice.external_invoice_id == external_id))
    ).scalar_one_or_none()

    if not invoice:
        return {"status": "ignored", "reason": "invoice_not_found"}

    if invoice.status == "paid":
        return {"status": "success", "reason": "already_paid"}

    invoice.status = "paid"
    invoice.paid_at = datetime.now()

    user = (await db.execute(select(User).where(User.id == invoice.user_id))).scalar_one_or_none()
    if user:
        user.subscription_tier = invoice.tier_code

    await db.flush()
    return {"status": "success", "user_id": str(invoice.user_id), "upgraded_tier": invoice.tier_code}
