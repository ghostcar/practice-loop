"""Media Vault page (DESIGN v2 §10/§11) — SSR gallery.

GET   /media                 — gallery: large images (min 160×120), date, type,
                               provenance, verified state (LLM results), retention
POST  /media/upload          — stage a new upload (owner_type=general)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.media import ALLOWED_OWNER_TYPES
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.activity_log import ActivityLog
from app.models.life import InventoryItem
from app.models.media import MediaAsset, MediaVerificationResult
from app.models.user import User
from app.services.media import save_media
from app.templates_setup import templates

router = APIRouter(tags=["media-vault"])


async def _verification_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, dict]:
    """Latest LLM verification result per media asset (verdict badge)."""
    stmt = (
        select(MediaVerificationResult)
        .where(MediaVerificationResult.owner_id == user_id)
        .order_by(MediaVerificationResult.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    out: dict[str, dict] = {}
    for r in rows:
        key = str(r.media_id)
        if key not in out:
            out[key] = {
                "verdict": r.verdict,
                "verification_type": r.verification_type,
                "confidence": r.confidence,
            }
    return out


async def _provenance_map(db: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    """Resolve owner_ref_id → short human label for common owner types."""
    labels: dict[str, str] = {}

    inv_stmt = select(InventoryItem).where(InventoryItem.user_id == user_id)
    for item in (await db.execute(inv_stmt)).scalars().all():
        labels[f"inventory_item:{item.id}"] = item.name or item.id[:8]

    log_stmt = select(ActivityLog).where(ActivityLog.user_id == user_id)
    for log in (await db.execute(log_stmt)).scalars().all():
        name = log.title_override or log.selected_entity_name
        if name:
            labels[f"activity_log:{log.id}"] = name

    return labels


@router.get("/media", response_class=HTMLResponse)
async def media_vault_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    stmt = select(MediaAsset).where(MediaAsset.owner_id == user.id).order_by(MediaAsset.created_at.desc()).limit(100)
    asset_rows = (await db.execute(stmt)).scalars().all()

    verification = await _verification_map(db, user.id)
    provenance = await _provenance_map(db, user.id)

    items = []
    for a in asset_rows:
        ref_key = f"{a.owner_type}:{a.owner_ref_id}" if a.owner_ref_id else None
        items.append(
            {
                "id": str(a.id),
                "owner_type": a.owner_type,
                "owner_ref_id": str(a.owner_ref_id) if a.owner_ref_id else None,
                "state": a.state,
                "mime_type": a.mime_type,
                "file_size_bytes": a.file_size_bytes,
                "caption": a.caption,
                "original_filename": a.original_filename,
                "has_thumbnail": a.thumbnail_path is not None,
                "is_image": (a.mime_type or "").startswith("image/"),
                "created_at": a.created_at,
                "provenance": provenance.get(ref_key or "", ""),
                "verification": verification.get(str(a.id)),
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="media_vault.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "items": items,
            "owner_types": sorted(ALLOWED_OWNER_TYPES),
        },
    )


@router.post("/media/upload")
async def media_vault_upload(
    request: Request,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stage a new upload from the vault (bound later from domain pages)."""
    info = await save_media(file)
    asset = MediaAsset(
        owner_id=user.id,
        owner_type="general",
        state="staged",
        file_path=info["file_path"],
        thumbnail_path=info["thumbnail_path"],
        original_filename=info["original_filename"],
        mime_type=info["mime_type"],
        file_size_bytes=info["file_size_bytes"],
        sha256_hex=info["sha256_hex"],
        width=info["width"],
        height=info["height"],
        caption=(caption or "").strip()[:500] or None,
    )
    db.add(asset)

    # OCR extraction (ADR-181): extract text/tag from uploaded photo (§C.4)
    if asset.mime_type and asset.mime_type.startswith("image/"):
        try:
            from pathlib import Path

            from app.config import settings
            from app.media.ocr_seals import extract_seal_tag_from_photo

            fp = asset.file_path
            if fp and fp.startswith("/uploads/"):
                rel = fp[len("/uploads/") :]
                disk = (Path(settings.upload_dir).resolve() / rel).resolve()
                if str(disk).startswith(str(Path(settings.upload_dir).resolve()) + "/") and disk.is_file():
                    ocr_result = extract_seal_tag_from_photo(disk.read_bytes())
                    tag = ocr_result.get("extracted_tag")
                    if tag and not asset.caption:
                        asset.caption = f"OCR: {tag}"[:500]
        except Exception:
            pass  # OCR is best-effort, never fail upload

    await db.flush()
    return RedirectResponse(url="/media", status_code=303)


@router.get("/media/progress", response_class=HTMLResponse)
async def media_progress_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Photo progress timeline & side-by-side comparison workbench (Step 28)."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    stmt = (
        select(MediaAsset)
        .where(MediaAsset.owner_id == user.id, MediaAsset.state != "archived")
        .order_by(MediaAsset.created_at.desc())
    )
    items = (await db.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="media_progress.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "media",
            "items": items,
        },
    )


json_router = APIRouter(prefix="/api/v2/media", tags=["media-verify-llm"])


@json_router.post("/verify-llm")
async def json_verify_photo_llm(
    media_id: uuid.UUID = Form(...),
    verification_type: str = Form(default="code_match"),
    expected_details: str = Form(default="Chastity seal tag verification"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """LLM Photo Verification Engine (AI Controller / Keyholder / Top — Step 28)."""
    from app.llm.pipeline import get_active_llm_config
    from app.llm.pipeline.photo_verifier import verify_photo_with_llm

    llm_config = await get_active_llm_config(db, user.id, "vision")
    if not llm_config:
        from fastapi import HTTPException

        raise HTTPException(400, "LLM provider config required for AI Photo Verification")

    res = await verify_photo_with_llm(
        db=db,
        user_id=user.id,
        media_id=media_id,
        verification_type=verification_type,
        expected_details=expected_details,
        llm_config=llm_config,
        locale=user.locale or "ru",
    )
    return res


@json_router.post("/recognize-inventory")
async def json_recognize_inventory_photo(
    media_id: uuid.UUID = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI Inventory Auto-Recognition & Auto-Fill from Photo (Step 29)."""
    from app.llm.pipeline import get_active_llm_config
    from app.llm.pipeline.photo_verifier import recognize_inventory_from_photo

    llm_config = await get_active_llm_config(db, user.id, "vision")
    if not llm_config:
        from fastapi import HTTPException

        raise HTTPException(400, "LLM provider config required for AI Inventory Recognition")

    item_data = await recognize_inventory_from_photo(
        db=db,
        user_id=user.id,
        media_id=media_id,
        llm_config=llm_config,
        locale=user.locale or "ru",
    )
    return item_data
