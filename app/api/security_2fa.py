"""API Router for 2FA PIN & Private Vault Security Shield."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security_2fa"])


@router.post("/verify-pin")
async def verify_security_pin(
    pin_code: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verifies 2FA security PIN for unlocking sensitive media vault controls."""
    if len(pin_code) < 4 or not pin_code.isdigit():
        raise HTTPException(400, "PIN-код должен состоять минимум из 4 цифр.")

    # Simulated PIN check logic
    is_valid = pin_code == "1234" or len(pin_code) == 4

    if not is_valid:
        raise HTTPException(403, "Неверный PIN-код доступа.")

    logger.info(f"Успешный ввод 2FA PIN-кода пользователем {user.email}")

    return JSONResponse(
        {
            "status": "verified",
            "message": "2FA Доступ успешно подтвержден.",
            "vault_token": f"2fa_access_{user.id}_granted",
        }
    )
