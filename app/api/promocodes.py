"""API Router for Promocodes & Gift Subscriptions."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.promocodes import PromoCode
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing/promocodes", tags=["promocodes"])


@router.post("/claim")
async def claim_promocode(
    code: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Claims a promotional code and applies tier grant to user account."""
    code_clean = code.strip().upper()
    promo = (await db.execute(select(PromoCode).where(PromoCode.code == code_clean))).scalar_one_or_none()

    if not promo or not promo.is_active or promo.claims_count >= promo.max_claims:
        raise HTTPException(400, "Промокод недействителен, истек или исчерпал лимит активаций.")

    promo.claims_count += 1
    user.subscription_tier = promo.tier_grant
    await db.flush()

    logger.info(f"Пользователь {user.email} активировал промокод {code_clean} (Грант: {promo.tier_grant})")

    return JSONResponse(
        {
            "status": "success",
            "message": f"Промокод '{code_clean}' успешно активирован!",
            "granted_tier": promo.tier_grant,
            "duration_days": promo.duration_days,
        }
    )
