"""Chastity wear check-ins API (C2 + B3/Q13, PRODUCT_OVERVIEW §6.6).

Регулярный check-in ношения: состояние/комфорт/отчёт + опциональная
LLM-верификация фото (chastity_closed/code_match) через media_verify.
Relief-only (PD-013).

JSON API (мобильный/bearer):
- GET    /api/v2/chastity/check-ins            — список (фильтр по session_id)
- POST   /api/v2/chastity/check-ins            — создать (201)
- DELETE /api/v2/chastity/check-ins/{id}       — удалить (204)
- POST   /api/v2/chastity/check-ins/{id}/verify — LLM-верификация фото (B3)

Form (HTMX):
- POST /chastity-checkins — создать check-in → redirect
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.llm.pipeline import get_active_llm_config
from app.llm.pipeline.media_verify import find_active_challenge, verify_media_with_llm
from app.models.chastity import ChastityCheckIn
from app.models.media import MediaAsset
from app.models.user import User

router = APIRouter(tags=["chastity"])
json_router = APIRouter(prefix="/api/v2/chastity", tags=["chastity"])


def _checkin_dict(c: ChastityCheckIn) -> dict:
    return {
        "id": str(c.id),
        "session_id": str(c.session_id) if c.session_id else None,
        "mood": c.mood,
        "comfort_level": c.comfort_level,
        "notes": c.notes,
        "media_id": str(c.media_id) if c.media_id else None,
        "verification_result_id": str(c.verification_result_id) if c.verification_result_id else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _parse_scale(raw: str, field: str) -> int | None:
    if not raw.strip():
        return None
    try:
        v = int(raw)
    except ValueError:
        raise HTTPException(400, f"Invalid {field} (1-5)") from None
    if not 1 <= v <= 5:
        raise HTTPException(400, f"Invalid {field} (1-5)")
    return v


# ─────────────────────────────────────────────────────────────────────────────
# Form handler (HTMX)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/chastity-checkins")
async def add_checkin_form(
    request: Request,
    session_id: str = Form(default=""),
    mood: str = Form(default=""),
    comfort_level: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sess_id = uuid.UUID(session_id) if session_id.strip() else None
    if sess_id is not None:
        from app.locktimer.repositories import get_session

        if await get_session(db, sess_id, user.id) is None:
            raise HTTPException(400, "Session not found")

    c = ChastityCheckIn(
        user_id=user.id,
        session_id=sess_id,
        mood=_parse_scale(mood, "mood"),
        comfort_level=_parse_scale(comfort_level, "comfort_level"),
        notes=(notes or "").strip() or None,
    )
    db.add(c)
    await db.flush()
    back = request.headers.get("referer") or "/locktimer"
    return RedirectResponse(url=back, status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("/check-ins")
async def json_list_checkins(
    session_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(ChastityCheckIn).where(ChastityCheckIn.user_id == user.id)
    if session_id is not None:
        query = query.where(ChastityCheckIn.session_id == session_id)
    rows = (await db.execute(query.order_by(ChastityCheckIn.created_at.desc()))).scalars().all()
    return [_checkin_dict(c) for c in rows]


class CheckInBody(BaseModel):
    session_id: uuid.UUID | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    comfort_level: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None
    media_id: uuid.UUID | None = None


@json_router.post("/check-ins", status_code=201)
async def json_add_checkin(
    body: CheckInBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.session_id is not None:
        from app.locktimer.repositories import get_session

        if await get_session(db, body.session_id, user.id) is None:
            raise HTTPException(400, "Session not found")

    media_id = None
    if body.media_id is not None:
        media = (
            await db.execute(select(MediaAsset).where(MediaAsset.id == body.media_id, MediaAsset.owner_id == user.id))
        ).scalar_one_or_none()
        if media is None:
            raise HTTPException(400, "Media not found")
        media_id = body.media_id

    c = ChastityCheckIn(
        user_id=user.id,
        session_id=body.session_id,
        mood=body.mood,
        comfort_level=body.comfort_level,
        notes=(body.notes or "").strip() or None,
        media_id=media_id,
    )
    db.add(c)
    await db.flush()
    return _checkin_dict(c)


@json_router.delete("/check-ins/{checkin_id}", status_code=204)
async def json_delete_checkin(
    checkin_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = (
        await db.execute(
            select(ChastityCheckIn).where(ChastityCheckIn.id == checkin_id, ChastityCheckIn.user_id == user.id)
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "Check-in not found")
    await db.delete(c)
    await db.flush()
    return None


class VerifyCheckInBody(BaseModel):
    verification_type: str = "chastity_closed"  # chastity_closed | code_match
    expected_code: str | None = None
    auto_consume_challenge: bool = True


@json_router.post("/check-ins/{checkin_id}/verify")
async def json_verify_checkin(
    checkin_id: uuid.UUID,
    body: VerifyCheckInBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run LLM photo verification for a check-in photo (B3/Q13)."""
    c = (
        await db.execute(
            select(ChastityCheckIn).where(ChastityCheckIn.id == checkin_id, ChastityCheckIn.user_id == user.id)
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "Check-in not found")
    if c.media_id is None:
        raise HTTPException(400, "Check-in has no photo to verify")

    media = (
        await db.execute(select(MediaAsset).where(MediaAsset.id == c.media_id, MediaAsset.owner_id == user.id))
    ).scalar_one_or_none()
    if media is None or media.state != "ready":
        raise HTTPException(409, "Media not ready")

    if body.verification_type not in ("chastity_closed", "code_match"):
        raise HTTPException(400, "Unsupported verification_type")

    llm_config = await get_active_llm_config(db, user.id, "vision")
    if llm_config is None:
        raise HTTPException(409, "No active LLM provider config")

    challenge = None
    resolved_expected = body.expected_code
    if body.verification_type == "code_match" and not resolved_expected:
        challenge = await find_active_challenge(db, user.id, "chastity_check_in", c.id)
        if challenge is None:
            raise HTTPException(400, "expected_code is required when there is no active challenge")

    result = await verify_media_with_llm(
        db=db,
        user_id=user.id,
        llm_config=llm_config,
        media=media,
        verification_type=body.verification_type,
        expected_code=resolved_expected,
        locale=user.locale or "en",
        challenge=challenge,
    )

    consumed = None
    if challenge is not None and body.auto_consume_challenge and result.verdict == "match":
        from datetime import UTC, datetime

        challenge.state = "consumed"
        challenge.consumed_at = datetime.now(UTC)
        result.consumed_challenge_id = challenge.id
        consumed = challenge

    c.verification_result_id = result.id
    await db.flush()
    await db.refresh(result)
    return {
        "check_in_id": str(c.id),
        "verification_result": {
            "id": str(result.id),
            "verification_type": result.verification_type,
            "verdict": result.verdict,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
        },
        "consumed_challenge": {"id": str(consumed.id), "state": "consumed"} if consumed is not None else None,
    }
