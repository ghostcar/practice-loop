"""API Router for User Billing Showcase & Multi-Gateway Checkout."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.billing.gateways import create_payment_checkout_session, process_payment_webhook
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.monetization import SubscriptionTier, TemporaryFeaturePromotion
from app.models.payment import PaymentInvoice
from app.models.user import User
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])


@router.get("/billing", response_class=HTMLResponse)
async def user_billing_showcase_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User Billing Showcase UI Page."""
    tiers_res = await db.execute(select(SubscriptionTier).order_by(SubscriptionTier.rank.asc()))
    tiers = tiers_res.scalars().all()

    promos_res = await db.execute(
        select(TemporaryFeaturePromotion).where(TemporaryFeaturePromotion.is_active.is_(True))
    )
    active_promos = promos_res.scalars().all()

    invoices_res = await db.execute(
        select(PaymentInvoice)
        .where(PaymentInvoice.user_id == user.id)
        .order_by(PaymentInvoice.created_at.desc())
        .limit(5)
    )
    user_invoices = invoices_res.scalars().all()

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="billing.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "billing",
            "tiers": tiers,
            "active_promos": active_promos,
            "user_invoices": user_invoices,
        },
    )


@router.post("/billing/checkout")
async def checkout_endpoint(
    tier_code: str = Form(...),
    gateway: str = Form("stripe"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiates checkout session for selected subscription tier and gateway."""
    result = await create_payment_checkout_session(db, user, tier_code=tier_code, gateway=gateway)
    return JSONResponse(result)


@router.post("/billing/webhook/{gateway}")
async def gateway_webhook_endpoint(
    gateway: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Processes payment gateway webhook notification."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    result = await process_payment_webhook(db, gateway=gateway, payload=payload)
    return JSONResponse(result)
