"""LLM media verification API (ADR-075, Step 7) + OCR engine (ADR-181, v0.9.1).

Endpoints:
- POST /api/v2/media/{asset_id}/verify        — JSON: запустить LLM-оценку фото
- POST /api/v2/media/ocr-extract              — JSON: извлечь текст/код из фото через OCR
- GET  /api/v2/media/{asset_id}/verification-results — история оценок для медиа
- GET  /llm/verify                            — страница: выбор медиа + форма + OCR-таб
- POST /llm/verify                            — форма: запустить оценку (LLM + OCR pre-flight)
- POST /llm/verify/ocr                        — форма: OCR-извлечение текста из фото

Логика (общая для JSON и формы):
- ``code_match``:
    - **OCR-first (ADR-181):** сначала локальный OCR (pytesseract) — если уверенность
      >= 0.90 и код найден, возвращаем результат без LLM-вызова;
    - если OCR не дал результата или низкая уверенность — fallback на LLM-vision;
    - если передан ``expected_code`` — сравнивает код на фото с ожидаемым;
    - если есть активный VerificationChallenge для owner медиа — читает код
      с фото, сервер сверяет HMAC (сервер — авторитет), при match и явном
      ``auto_consume`` challenge переводится в consumed;
    - иначе — 400 (нет основания для сравнения).
- ``chastity_closed`` — только LLM-vision (OCR не применим).

Вердикт LLM — вспомогательное доказательство; авторитетное завершение — HMAC.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
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
from app.media.ocr_seals import extract_seal_tag_from_photo
from app.models.media import MediaAsset, MediaVerificationResult, VerificationChallenge
from app.models.user import User
from app.templates_setup import templates

page_router = APIRouter(tags=["media-verify"])
json_router = APIRouter(prefix="/api/v2/media", tags=["media-verify"])
ocr_router = APIRouter(tags=["media-verify"])


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
        "method": getattr(r, "method", None) or "llm",
    }


async def _run_verification(
    db: AsyncSession,
    user: User,
    media: MediaAsset,
    verification_type: str,
    expected_code: str | None,
    auto_consume: bool,
    locale: str,
) -> tuple[MediaVerificationResult, VerificationChallenge | None, dict | None]:
    """Run verification (OCR-first for code_match, then LLM-vision).

    Returns (result_row, consumed_challenge_or_None, ocr_info_or_None).
    """
    from app.consent import require_consent

    await require_consent(db, user.id, "media_verification")
    if verification_type not in VALID_TYPES:
        raise HTTPException(400, f"Unsupported verification_type: {verification_type}")

    ocr_info: dict | None = None

    # ── OCR-first for code_match (ADR-181) ──
    if verification_type == "code_match":
        ocr_info = _try_ocr_media(media)
        if ocr_info and ocr_info.get("confidence", 0) >= 0.90:
            # OCR high-confidence: use directly, no LLM call needed
            return _build_ocr_result(db, user, media, ocr_info, expected_code, auto_consume, locale)

    challenge = None
    resolved_expected = expected_code
    # ── LLM fallback ──
    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        raise HTTPException(409, "No active LLM provider config — set one up in LLM Settings")
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
        ocr_info=ocr_info,
    )
    result.method = "llm"

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
    return result, consumed, ocr_info


def _media_bind_label(media: MediaAsset) -> str:
    if media.owner_ref_id:
        return f"{media.owner_type}:{media.owner_ref_id}"
    return media.owner_type or "general"


def _try_ocr_media(media: MediaAsset) -> dict | None:
    """Attempt OCR on a media asset's file. Returns None if file missing."""
    from pathlib import Path

    from app.config import settings

    if not media.file_path or not media.file_path.startswith("/uploads/"):
        return None
    rel = media.file_path[len("/uploads/") :]
    candidate = (Path(settings.upload_dir).resolve() / rel).resolve()
    if not str(candidate).startswith(str(Path(settings.upload_dir).resolve()) + "/"):
        return None
    if not candidate.is_file():
        return None
    try:
        data = candidate.read_bytes()
        return extract_seal_tag_from_photo(data)
    except Exception:
        return None


async def _build_ocr_result(
    db: AsyncSession,
    user: User,
    media: MediaAsset,
    ocr_info: dict,
    expected_code: str | None,
    auto_consume: bool,
    locale: str,
) -> tuple[MediaVerificationResult, object | None, dict | None]:
    """Build a MediaVerificationResult from high-confidence OCR."""
    from app.services.media import compute_code_hmac

    is_match = ocr_info.get("is_match", False)
    confidence = int(ocr_info.get("confidence", 0) * 100)
    extracted = ocr_info.get("extracted_tag")
    reasoning = ocr_info.get("notes", f"OCR extracted: {extracted or 'none'}")

    verdict = "match" if is_match else ("unclear" if not extracted else "mismatch")

    expected_hmac = compute_code_hmac(expected_code) if expected_code else None

    row = MediaVerificationResult(
        owner_id=user.id,
        media_id=media.id,
        verification_type="code_match",
        expected_code_hmac=expected_hmac,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning[:2000] or None,
        llm_model="ocr:pytesseract",
    )
    db.add(row)
    await db.flush()
    row.method = "ocr"
    consumed = None  # OCR doesn't auto-consume challenges yet
    return row, consumed, ocr_info


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

    result_row, consumed, _ocr = await _run_verification(
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

    result_row, consumed, _ocr = await _run_verification(
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


# ---------------------------------------------------------------------------
# OCR extract endpoints (ADR-181)
# ---------------------------------------------------------------------------


@ocr_router.post("/api/v2/media/ocr-extract")
async def ocr_extract_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Extract seal tag / text from a photo via local OCR (no LLM)."""
    photo_bytes = await file.read()
    result = extract_seal_tag_from_photo(photo_bytes)
    return {"status": "success", **result}


@page_router.post("/llm/verify/ocr")
async def ocr_verify_form(
    request: Request,
    photo: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """OCR form: загрузить фото → извлечь текст через OCR."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    photo_bytes = await photo.read()
    ocr_result = extract_seal_tag_from_photo(photo_bytes)

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
            "ocr_result": {
                "extracted_tag": ocr_result.get("extracted_tag"),
                "confidence": int(ocr_result.get("confidence", 0) * 100),
                "is_match": ocr_result.get("is_match", False),
                "low_confidence": ocr_result.get("low_confidence", True),
                "raw_ocr_snippet": ocr_result.get("raw_ocr_snippet", ""),
                "notes": ocr_result.get("notes", ""),
            },
        },
    )
