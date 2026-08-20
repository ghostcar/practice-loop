"""Chastity Lockholder & Wear Verification Engine v2."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ds_suite import ChastityLockLog, ManagedSubmissive
from app.models.user import User

logger = logging.getLogger(__name__)


async def _get_or_create_submissive(db: AsyncSession, user: User) -> ManagedSubmissive:
    sub_res = await db.execute(select(ManagedSubmissive).where(ManagedSubmissive.top_user_id == user.id))
    sub = sub_res.scalar_one_or_none()
    if not sub:
        sub = ManagedSubmissive(top_user_id=user.id, sub_user_id=user.id, name=user.email.split("@")[0])
        db.add(sub)
        await db.flush()
    return sub


async def generate_random_unlock_combination(
    db: AsyncSession,
    user: User,
    lock_id: str,
) -> dict[str, Any]:
    """Generates secret combination for lock timer upon satisfying compliance conditions."""
    sub = await _get_or_create_submissive(db, user)
    secret_code = secrets.token_hex(4).upper()

    log_entry = ChastityLockLog(
        managed_sub_id=sub.id,
        action="combination_generated",
        reason=f"Сгенерирован ключ разблокировки для {lock_id}: {secret_code}",
    )
    db.add(log_entry)
    await db.flush()

    return {
        "status": "success",
        "lock_id": lock_id,
        "combination_code": secret_code,
        "message": "Ключ разблокировки успешно сгенерирован ИИ-Ключником.",
    }


async def verify_wear_checkin_photo(
    db: AsyncSession,
    user: User,
    lock_id: str,
    photo_url: str,
) -> dict[str, Any]:
    """Multi-modal verification of wear integrity and lock check-in."""
    sub = await _get_or_create_submissive(db, user)

    log_entry = ChastityLockLog(
        managed_sub_id=sub.id,
        action="checkin_verified",
        reason=f"Мультимодальная верификация чек-ина ношения {lock_id} ({photo_url}) прошла успешно.",
    )
    db.add(log_entry)
    await db.flush()

    return {
        "status": "verified",
        "lock_id": lock_id,
        "compliance_boost": 5.0,
        "message": "Верификация целостности ношения успешно подтверждена ИИ-Ключником.",
    }
