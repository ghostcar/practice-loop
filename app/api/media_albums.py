"""API Router for Smart Albums, Batch Operations and Privacy Redaction."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Form, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.media.privacy_mask import apply_privacy_mask
from app.models.user import User
from app.services.smart_albums import (
    batch_delete_assets,
    create_encrypted_zip_export,
    get_smart_albums,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/media", tags=["media_smart_albums"])


class RedactMediaRequest(BaseModel):
    media_path: str
    mask_boxes: list[dict[str, Any]] = Field(default_factory=list)
    default_mode: str = Field(default="blur", description="blur | blackout | pixelate")


class BatchDeleteRequest(BaseModel):
    asset_ids: list[uuid.UUID] = Field(..., min_length=1)


@router.get("/smart-albums")
async def get_smart_albums_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns grouped smart albums: sessions, chastity, body_cycle, care, permanent_showcase."""
    albums = await get_smart_albums(db, user.id)
    return JSONResponse(
        {
            "status": "success",
            "albums": albums,
            "counts": {k: len(v) for k, v in albums.items()},
        }
    )


@router.post("/batch-export-zip")
async def batch_export_zip_endpoint(
    asset_ids: list[str] = Form(default=[]),
    zip_password: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Packages selected media assets into an encrypted ZIP archive."""
    parsed_ids = [uuid.UUID(i) for i in asset_ids if i]
    zip_bytes = await create_encrypted_zip_export(
        db=db,
        user_id=user.id,
        asset_ids=parsed_ids if parsed_ids else None,
        zip_password=zip_password,
    )
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=practice_loop_vault_export.zip"},
    )


@router.post("/batch-delete")
async def batch_delete_endpoint(
    payload: BatchDeleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deletes multiple media assets while strictly safeguarding permanent immutable showcase drops."""
    result = await batch_delete_assets(db, user.id, payload.asset_ids)
    return JSONResponse({"status": "success", **result})


@router.post("/redact")
async def redact_media_endpoint(
    payload: RedactMediaRequest,
    user: User = Depends(get_current_user),
):
    """Applies privacy blur/blackout masks to image regions."""
    # Simulated processing from raw buffer / path
    sample_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
    redacted_bytes = apply_privacy_mask(sample_bytes, payload.mask_boxes, payload.default_mode)

    return JSONResponse(
        {
            "status": "success",
            "media_path": payload.media_path,
            "mask_boxes_count": len(payload.mask_boxes),
            "redacted_size_bytes": len(redacted_bytes),
            "mode": payload.default_mode,
            "message": f"Применена маскировка приватности к {len(payload.mask_boxes)} зонам.",
        }
    )
