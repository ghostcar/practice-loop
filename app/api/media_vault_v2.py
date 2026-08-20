"""API Router for Media Vault Security v2 (One-Time Burn-on-Read Tokens)."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.media_vault import OneTimeMediaToken
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media_vault_v2"])


@router.post("/one-time-token")
async def create_one_time_media_token_endpoint(
    media_path: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a self-destructing burn-on-read media viewing token."""
    token_code = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=24)

    token_entry = OneTimeMediaToken(
        user_id=user.id,
        token=token_code,
        media_path=media_path,
        is_burned=False,
        expires_at=expires_at,
    )
    db.add(token_entry)
    await db.flush()

    return JSONResponse(
        {
            "status": "success",
            "token": token_code,
            "view_url": f"/media/view-once/{token_code}",
            "expires_at": expires_at.isoformat(),
        }
    )


@router.get("/view-once/{token}")
async def view_once_media_endpoint(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Renders photo proof and burns token immediately (Burn-on-Read)."""
    token_entry = (
        await db.execute(
            select(OneTimeMediaToken).where(
                OneTimeMediaToken.token == token,
                OneTimeMediaToken.is_burned == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()

    if not token_entry:
        raise HTTPException(404, "Ссылка недействительна или файл уже самоуничтожен.")

    exp = token_entry.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)

    if datetime.now(UTC) > exp:
        token_entry.is_burned = True
        await db.flush()
        raise HTTPException(410, "Срок действия одноразовой ссылки истек.")

    # Burn immediately on read
    token_entry.is_burned = True
    await db.flush()

    return JSONResponse(
        {
            "status": "burned",
            "media_path": token_entry.media_path,
            "message": "Ссылка успешно уничтожена после первого просмотра.",
        }
    )
