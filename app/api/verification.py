"""Verification challenge API — platform-level, not OCR-dependent.

POST   /api/v1/verification/challenges            — create a challenge
POST   /api/v1/verification/challenges/{id}/verify — verify a code
GET    /api/v1/verification/challenges/{id}         — status (code never returned)

OCR support deferred for future iteration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.media import VerificationChallenge
from app.models.user import User
from app.services.media import (
    compute_code_hmac,
    generate_verification_code,
    verify_code_constant_time,
)

router = APIRouter(prefix="/api/v1/verification", tags=["verification"])

DEFAULT_TTL_MINUTES = 10
DEFAULT_CODE_LENGTH = 7
DEFAULT_MAX_ATTEMPTS = 5


class ChallengeRequest(BaseModel):
    owner_type: str
    owner_ref_id: uuid.UUID
    code_length: int = Field(default=DEFAULT_CODE_LENGTH, ge=4, le=16)
    ttl_minutes: int = Field(default=DEFAULT_TTL_MINUTES, ge=2, le=30)
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1, le=20)


class VerifyRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)


def _serialize(c: VerificationChallenge, include_code: bool = False) -> dict:
    result = {
        "id": str(c.id),
        "owner_type": c.owner_type,
        "owner_ref_id": str(c.owner_ref_id),
        "state": c.state,
        "code_length": c.code_length,
        "attempt_count": c.attempt_count,
        "max_attempts": c.max_attempts,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "consumed_at": c.consumed_at.isoformat() if c.consumed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
    # Code is returned exactly once — at creation time.
    # No other endpoint or serialization path exposes it.
    if include_code:
        result["code"] = None  # placeholder — actual code injected at creation
    return result


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post("/challenges")
async def create_challenge(
    body: ChallengeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a verification challenge. The plaintext code is returned ONCE here."""
    now = datetime.now(UTC)
    code = generate_verification_code(body.code_length)
    hmac_value = compute_code_hmac(code)

    # Invalidate any previous active challenges for the same owner_ref
    existing_result = await db.execute(
        select(VerificationChallenge).where(
            VerificationChallenge.owner_id == user.id,
            VerificationChallenge.owner_type == body.owner_type,
            VerificationChallenge.owner_ref_id == body.owner_ref_id,
            VerificationChallenge.state == "active",
        )
    )
    for old in existing_result.scalars().all():
        old.state = "expired"

    challenge = VerificationChallenge(
        owner_id=user.id,
        owner_type=body.owner_type,
        owner_ref_id=body.owner_ref_id,
        code_hmac=hmac_value,
        code_length=body.code_length,
        state="active",
        max_attempts=body.max_attempts,
        attempt_count=0,
        expires_at=now + timedelta(minutes=body.ttl_minutes),
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)

    response = _serialize(challenge)
    response["code"] = code  # returned only here
    return response


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


@router.post("/challenges/{challenge_id}/verify")
async def verify_challenge(
    challenge_id: uuid.UUID,
    body: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit a code for verification. Constant-time comparison."""
    now = datetime.now(UTC)

    result = await db.execute(
        select(VerificationChallenge).where(
            VerificationChallenge.id == challenge_id,
            VerificationChallenge.owner_id == user.id,
        )
    )
    challenge = result.scalar_one_or_none()
    if challenge is None:
        raise HTTPException(404, "Challenge not found")

    # State checks
    if challenge.state == "consumed":
        raise HTTPException(409, "Challenge already consumed")
    if challenge.state == "failed":
        raise HTTPException(409, "Challenge has been failed (max attempts reached)")
    expires = challenge.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if challenge.state == "expired" or expires < now:
        if challenge.state == "active":
            challenge.state = "expired"
            await db.commit()
        raise HTTPException(410, "Challenge has expired")

    # Increment attempt count
    challenge.attempt_count += 1

    # Constant-time comparison
    if verify_code_constant_time(body.code, challenge.code_hmac):
        challenge.state = "consumed"
        challenge.consumed_at = now
        await db.commit()
        return {"verified": True, "state": "consumed"}

    # Wrong code
    if challenge.attempt_count >= challenge.max_attempts:
        challenge.state = "failed"
        await db.commit()
        raise HTTPException(403, "Verification failed — max attempts reached")

    await db.commit()
    raise HTTPException(403, f"Invalid code ({challenge.attempt_count}/{challenge.max_attempts} attempts)")


# ---------------------------------------------------------------------------
# Status (code never returned)
# ---------------------------------------------------------------------------


@router.get("/challenges/{challenge_id}")
async def get_challenge_status(
    challenge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get verification challenge status. The code is NEVER returned."""
    result = await db.execute(
        select(VerificationChallenge).where(
            VerificationChallenge.id == challenge_id,
            VerificationChallenge.owner_id == user.id,
        )
    )
    challenge = result.scalar_one_or_none()
    if challenge is None:
        raise HTTPException(404, "Challenge not found")

    # Auto-expire if TTL passed
    now = datetime.now(UTC)
    expires = challenge.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if challenge.state == "active" and expires < now:
        challenge.state = "expired"
        await db.commit()

    return _serialize(challenge)
