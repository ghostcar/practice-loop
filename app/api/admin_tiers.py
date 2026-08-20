"""Admin API Router for Dynamic Subscription Tier Constructor & Temporary Promotions."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.monetization import SubscriptionTier, TemporaryFeaturePromotion, TierFeatureGrant
from app.models.user import User
from app.templates_setup import templates
from app.tier_guard import seed_default_tiers_and_grants

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin_tiers"])

FEATURE_CODES_LIST = [
    ("llm_exchange", "Экспорт в Внешнюю ИИ-Модель"),
    ("agent_chat", "PracticeLoop ИИ-Агент"),
    ("insights_analytics", "Аналитический Движок (10 Модулей)"),
    ("ds_portal", "D/s Command Center"),
    ("community_agent", "ИИ-Верхний Сообщества"),
]


@router.get("/admin/tiers", response_class=HTMLResponse)
async def admin_tiers_constructor_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Interactive Tier Constructor UI Page for Admins."""
    if user.role != "admin":
        raise HTTPException(403, "Admin privileges required")

    await seed_default_tiers_and_grants(db)

    tiers_res = await db.execute(select(SubscriptionTier).order_by(SubscriptionTier.rank.asc()))
    tiers = tiers_res.scalars().all()

    promos_res = await db.execute(
        select(TemporaryFeaturePromotion).order_by(TemporaryFeaturePromotion.created_at.desc())
    )
    promos = promos_res.scalars().all()

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="admin_tiers.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "admin_tiers",
            "tiers": tiers,
            "feature_codes": FEATURE_CODES_LIST,
            "promos": promos,
        },
    )


@router.post("/admin/tiers/save-matrix")
async def save_tier_matrix_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Saves dynamic feature grant matrix updates."""
    if user.role != "admin":
        raise HTTPException(403, "Admin privileges required")

    form_data = await request.form()

    # Clear existing grants and rebuild from matrix form
    await db.execute(select(TierFeatureGrant))
    tiers_res = await db.execute(select(SubscriptionTier))
    tiers = tiers_res.scalars().all()

    for tier in tiers:
        # Delete old grants for tier
        old_grants_res = await db.execute(select(TierFeatureGrant).where(TierFeatureGrant.tier_id == tier.id))
        for g in old_grants_res.scalars().all():
            await db.delete(g)

        for fc_code, _ in FEATURE_CODES_LIST:
            field_name = f"grant_{tier.code}_{fc_code}"
            if form_data.get(field_name) == "on":
                grant = TierFeatureGrant(tier_id=tier.id, feature_code=fc_code)
                db.add(grant)

    await db.flush()
    return JSONResponse({"status": "ok", "message": "Матрица тиров успешно сохранена."})


@router.post("/admin/tiers/promotions/create")
async def create_promotion_endpoint(
    feature_code: str = Form(...),
    target_min_tier_code: str = Form("standard"),
    days: int = Form(7),
    description: str = Form("Акционный доступ"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launches a temporary promotional override for a feature code."""
    if user.role != "admin":
        raise HTTPException(403, "Admin privileges required")

    now = datetime.now()
    ends_at = now + timedelta(days=days)

    promo = TemporaryFeaturePromotion(
        feature_code=feature_code,
        target_min_tier_code=target_min_tier_code,
        description=description,
        starts_at=now,
        ends_at=ends_at,
        is_active=True,
    )
    db.add(promo)
    await db.flush()

    return JSONResponse({"status": "ok", "promo_id": str(promo.id), "feature_code": feature_code})


@router.post("/admin/users/{target_user_id}/toggle-exemption")
async def toggle_user_exemption_endpoint(
    target_user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggles is_monetization_exempt flag for a user."""
    if user.role != "admin":
        raise HTTPException(403, "Admin privileges required")

    u_uuid = uuid.UUID(target_user_id)
    target_user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()

    if not target_user:
        raise HTTPException(404, "User not found")

    target_user.is_monetization_exempt = not target_user.is_monetization_exempt
    return JSONResponse({"status": "ok", "is_monetization_exempt": target_user.is_monetization_exempt})
