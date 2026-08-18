"""LLM media verification API (ADR-075, Step 7) — фото-оценка через vision.

Endpoints:
- POST /api/v2/media/{asset_id}/verify        — JSON: запустить LLM-оценку фото
- GET  /api/v2/media/{asset_id}/verification-results — история оценок для медиа
- GET  /llm/verify                            — страница: выбор медиа + форма
- POST /llm/verify                            — форма: запустить оценку

Логика (общая для JSON и формы):
- ``code_match``:
    - если передан ``expected_code`` — LLM сравнивает код на фото с ожидаемым;
    - если есть активный VerificationChallenge для owner медиа — LLM читает код
      с фото, сервер сверяет HMAC (сервер — авторитет), при match и явном
      ``auto_consume`` challenge переводится в consumed;
    - иначе — 400 (нет основания для сравнения).
- ``chastity_closed`` — LLM оценивает, закрыт ли замок/устройство на фото.

Вердикт LLM — вспомогательное доказательство; авторитетное завершение — HMAC.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.pipeline.generate import get_active_llm_config
from app.llm.pipeline.media_verify import (
    VALID_TYPES,
    find_active_challenge,
    verify_media_with_llm,
)
from app.models.media import MediaAsset, MediaVerificationResult, VerificationChallenge
from app.models.user import User
from app.templates_setup import templates

page_router = APIRouter(tags=["media-verify"])
json_router = APIRouter(prefix="/api/v2/media", tags=["media-verify"])


class VerifyRequest(BaseModel):
    verification_type: str = Field(..., description="code_match | chastity_closed")
    expected_code: str | None = Field(default=None, min_length=1, max_length=32)
    auto_consume_challenge: bool = False
    locale: str | None = Field(default=None, max_length=8)


def _serialize_result(r: MediaVerificationResult) -> dict:
    return {
        "id": str(r.id),
        "media_id": str(r.media_id),
        "verification_type": r.verification_type,
        "verdict": r.verdict,
        "confidence": r.confidence,
        "reasoning": r.reasoning,
        "llm_model": r.llm_model,
        "consumed_challenge_id": str(r.consumed_challenge_id) if r.consumed_challenge_id else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _run_verification(
    db: AsyncSession,
    user: User,
    media: MediaAsset,
    verification_type: str,
    expected_code: str | None,
    auto_consume: bool,
    locale: str,
) -> tuple[MediaVerificationResult, VerificationChallenge | None]:
    """Run LLM verification, optionally consuming an active challenge."""
    from app.consent import require_consent

    await require_consent(db, user.id, "media_verification")
    if verification_type not in VALID_TYPES:
        raise HTTPException(400, f"Unsupported verification_type: {verification_type}")

    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        raise HTTPException(409, "No active LLM provider config — set one up in LLM Settings")

    challenge = None
    resolved_expected = expected_code
    if verification_type == "code_match" and not resolved_expected:
        # Try to bind an active challenge for the media owner (if any).
        if media.owner_ref_id is not None:
            challenge = await find_active_challenge(db, user.id, media.owner_type, media.owner_ref_id)
        if challenge is None:
            raise HTTPException(
                400,
                "expected_code is required when there is no active verification challenge for this media",
            )

    result = await verify_media_with_llm(
        db=db,
        user_id=user.id,
        llm_config=llm_config,
        media=media,
        verification_type=verification_type,
        expected_code=resolved_expected,
        locale=locale,
        challenge=challenge,
    )

    consumed = None
    if challenge is not None and auto_consume and result.verdict == "match":
        from datetime import UTC, datetime

        challenge.state = "consumed"
        challenge.consumed_at = datetime.now(UTC)
        result.consumed_challenge_id = challenge.id
        consumed = challenge

    # get_db() auto-commits after the endpoint (audit P1-5).
    await db.flush()
    await db.refresh(result)
    return result, consumed


def _media_bind_label(media: MediaAsset) -> str:
    if media.owner_ref_id:
        return f"{media.owner_type}:{media.owner_ref_id}"
    return media.owner_type or "general"


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------


@json_router.post("/{asset_id}/verify")
async def verify_media_json(
    asset_id: uuid.UUID,
    body: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run an LLM photo-evaluation for the given media asset (owner only)."""
    result = await db.execute(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(404, "Media asset not found")
    if media.state != "ready":
        raise HTTPException(409, "Only finalized (ready) media can be verified")

    result_row, consumed = await _run_verification(
        db,
        user,
        media,
        body.verification_type,
        body.expected_code,
        body.auto_consume_challenge,
        (body.locale or user.locale or "en"),
    )
    payload = _serialize_result(result_row)
    payload["consumed_challenge"] = {"id": str(consumed.id), "state": "consumed"} if consumed is not None else None
    return payload


@json_router.get("/{asset_id}/verification-results")
async def verification_results(
    asset_id: uuid.UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List verification results for a media asset (owner only)."""
    result = await db.execute(
        select(MediaVerificationResult)
        .where(MediaVerificationResult.owner_id == user.id, MediaVerificationResult.media_id == asset_id)
        .order_by(MediaVerificationResult.created_at.desc())
        .limit(min(limit, 100))
    )
    return [_serialize_result(r) for r in result.scalars().all()]


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


async def _page_data(db: AsyncSession, user: User) -> tuple[list[dict], list[dict]]:
    """Fetch media picker list + recent verification history for the page."""
    media_result = await db.execute(
        select(MediaAsset)
        .where(MediaAsset.owner_id == user.id, MediaAsset.state == "ready")
        .order_by(MediaAsset.created_at.desc())
        .limit(30)
    )
    media_list = [
        {
            "id": str(m.id),
            "owner_type": m.owner_type,
            "owner_ref_id": str(m.owner_ref_id) if m.owner_ref_id else None,
            "bind_label": _media_bind_label(m),
            "caption": m.caption,
            "mime_type": m.mime_type,
            "has_thumbnail": m.thumbnail_path is not None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in media_result.scalars().all()
    ]

    history_result = await db.execute(
        select(MediaVerificationResult)
        .where(MediaVerificationResult.owner_id == user.id)
        .order_by(MediaVerificationResult.created_at.desc())
        .limit(20)
    )
    history = []
    for r in history_result.scalars().all():
        item = _serialize_result(r)
        m = await db.get(MediaAsset, r.media_id)
        item["media_label"] = _media_bind_label(m) if m else str(r.media_id)
        history.append(item)
    return media_list, history


@page_router.get("/llm/verify", response_class=HTMLResponse)
async def verify_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Страница LLM-верификации медиа: выбор фото + форма + история."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    media_list, history = await _page_data(db, user)
    llm_config = await get_active_llm_config(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="media_verify.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "media_list": media_list,
            "history": history,
            "has_llm_config": llm_config is not None,
        },
    )


@page_router.post("/llm/verify")
async def verify_page_post(
    request: Request,
    media_id: uuid.UUID = Form(...),
    verification_type: str = Form(...),
    expected_code: str = Form(default=""),
    auto_consume: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Форма: запустить LLM-оценку и показать результат на странице."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(select(MediaAsset).where(MediaAsset.id == media_id, MediaAsset.owner_id == user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(404, "Media asset not found")
    if media.state != "ready":
        raise HTTPException(409, "Only finalized (ready) media can be verified")

    result_row, consumed = await _run_verification(
        db,
        user,
        media,
        verification_type,
        expected_code.strip() or None,
        auto_consume == "on",
        locale,
    )

    data = _serialize_result(result_row)
    data["consumed_challenge"] = bool(consumed)
    data["media_label"] = _media_bind_label(media)

    media_list, history = await _page_data(db, user)
    llm_config = await get_active_llm_config(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="media_verify.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "media_list": media_list,
            "history": history,
            "has_llm_config": llm_config is not None,
            "result": data,
        },
    )
