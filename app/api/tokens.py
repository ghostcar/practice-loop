"""JSON bearer-auth API — Mobile Foundation (M4, ADR-063/065).

Issue/refresh/revoke access+refresh tokens for API clients (mobile, bots).
Lives alongside the cookie session (``app/api/auth.py``): the cookie keeps the
web UI, these endpoints serve the JSON-first contract.

POST /api/v2/auth/token         — email+password → access + refresh tokens
POST /api/v2/auth/refresh       — rotate a refresh token → new access + refresh
POST /api/v2/auth/revoke        — revoke a refresh token by value
GET  /api/v2/auth/tokens        — list the caller's active refresh tokens
POST /api/v2/auth/tokens/{id}/revoke — revoke a refresh token by id
GET  /api/v2/auth/me            — current user profile (token sanity check)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    generate_refresh_token,
    get_current_user,
    hash_refresh_token,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models.api_token import ApiToken
from app.models.user import User
from app.timeutils import as_utc

router = APIRouter(prefix="/api/v2/auth", tags=["mobile-auth"])

ACCESS_EXPIRE_SECONDS = settings.jwt_expire_minutes * 60


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TokenRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)
    client_name: str | None = Field(default=None, max_length=100)
    platform: str | None = Field(default=None, max_length=30)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


def _token_response(raw_access: str, raw_refresh: str) -> dict:
    return {
        "access_token": raw_access,
        "token_type": "bearer",
        "expires_in": ACCESS_EXPIRE_SECONDS,
        "refresh_token": raw_refresh,
    }


def _serialize_token(t: ApiToken) -> dict:
    return {
        "id": str(t.id),
        "client_name": t.client_name,
        "platform": t.platform,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
        "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        "revoked": t.revoked_at is not None,
    }


async def _issue_refresh(
    db: AsyncSession,
    user_id: uuid.UUID,
    client_name: str | None,
    platform: str | None,
    rotated_from_id: uuid.UUID | None = None,
) -> tuple[str, ApiToken]:
    """Create a new refresh token (returns raw value + stored row)."""
    raw = generate_refresh_token()
    record = ApiToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw),
        client_name=(client_name or "").strip()[:100] or None,
        platform=(platform or "").strip()[:30] or None,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        rotated_from_id=rotated_from_id,
    )
    db.add(record)
    await db.flush()
    return raw, record


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/token")
async def issue_token(
    body: TokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange email+password for an access + refresh token pair."""
    email = body.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")

    raw_access = create_access_token(user.id)
    raw_refresh, _ = await _issue_refresh(db, user.id, body.client_name, body.platform)
    return _token_response(raw_access, raw_refresh)


@router.post("/refresh")
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rotate a refresh token: new access + new refresh, old refresh revoked."""
    token_hash = hash_refresh_token(body.refresh_token)
    result = await db.execute(select(ApiToken).where(ApiToken.token_hash == token_hash))
    record = result.scalar_one_or_none()

    now = datetime.now(UTC)
    if record is None or record.revoked_at is not None:
        raise HTTPException(401, "Invalid or revoked refresh token")
    # expires_at is stored timezone-aware; SQLite reads it back naive → normalize.
    if as_utc(record.expires_at) <= now:
        raise HTTPException(401, "Refresh token expired")

    # Rotate: revoke the presented token, mint a fresh pair.
    record.revoked_at = now
    record.last_used_at = now
    db.add(record)

    raw_access = create_access_token(record.user_id)
    raw_refresh, new_record = await _issue_refresh(
        db,
        record.user_id,
        record.client_name,
        record.platform,
        rotated_from_id=record.id,
    )
    return _token_response(raw_access, raw_refresh)


@router.post("/revoke")
async def revoke_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Revoke a refresh token by its value (idempotent)."""
    token_hash = hash_refresh_token(body.refresh_token)
    result = await db.execute(select(ApiToken).where(ApiToken.token_hash == token_hash))
    record = result.scalar_one_or_none()
    if record is None:
        # Idempotent: revoking an unknown token is a no-op success.
        return {"status": "revoked"}
    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        db.add(record)
    return {"status": "revoked"}


@router.get("/tokens")
async def list_tokens(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's refresh tokens (devices), most recent first."""
    result = await db.execute(select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc()))
    return [_serialize_token(t) for t in result.scalars().all()]


@router.post("/tokens/{token_id}/revoke")
async def revoke_token_by_id(
    token_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke one of the caller's refresh tokens by id."""
    result = await db.execute(select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id))
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(404, "Token not found")
    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        db.add(record)
    return {"status": "revoked", "id": str(record.id)}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    """Current user profile — a lightweight token sanity check for clients."""
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "locale": user.locale,
        "theme": user.theme,
        "timezone": user.timezone,
        "subscription_tier": user.subscription_tier,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
