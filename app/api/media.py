"""Universal media API — platform-level, not Timer-specific.

POST   /api/v2/media                  — staged upload
POST   /api/v2/media/{id}/finalize    — staged → ready (bind to owner_ref)
GET    /api/v2/media/{id}             — authorized stream
GET    /api/v2/media/{id}/thumbnail   — authorized thumbnail
DELETE /api/v2/media/{id}             — owner-only delete (staged only)
GET    /api/v2/media                  — list user's media (paginated)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.media import MediaAsset
from app.models.user import User
from app.services.media import delete_media_file, save_media

router = APIRouter(prefix="/api/v2/media", tags=["media"])

# Allowlist: owner types that can bind media assets.
ALLOWED_OWNER_TYPES = {
    "activity_log",
    "training_day",
    "training_log_entry",
    "inventory_item",
    "diet",
    "measurement",
    "lock_session",
    "lock_slot_occurrence",
    "lock_task_occurrence",
    "social_publication",
    "journal_entry",
    "care_entry",
}


def _serialize(a: MediaAsset) -> dict:
    return {
        "id": str(a.id),
        "owner_type": a.owner_type,
        "owner_ref_id": str(a.owner_ref_id) if a.owner_ref_id else None,
        "state": a.state,
        "mime_type": a.mime_type,
        "file_size_bytes": a.file_size_bytes,
        "sha256_hex": a.sha256_hex,
        "width": a.width,
        "height": a.height,
        "caption": a.caption,
        "original_filename": a.original_filename,
        "sort_order": a.sort_order,
        "has_thumbnail": a.thumbnail_path is not None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ---------------------------------------------------------------------------
# Upload (staged)
# ---------------------------------------------------------------------------


@router.post("")
async def upload_media(
    file: UploadFile = File(...),
    owner_type: str = Query(default="general"),
    caption: str | None = Query(default=None, max_length=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stage a new media upload. Not yet bound to a domain object."""
    if owner_type not in ALLOWED_OWNER_TYPES and owner_type != "general":
        raise HTTPException(400, f"Unsupported owner_type: {owner_type}")

    info = await save_media(file)
    asset = MediaAsset(
        owner_id=user.id,
        owner_type=owner_type,
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
    # get_db() auto-commits after the endpoint (audit P1-5) — flush only to
    # materialize defaults/ids for the response.
    await db.flush()
    await db.refresh(asset)
    return _serialize(asset)


# ---------------------------------------------------------------------------
# Finalize: bind staged asset to a domain object
# ---------------------------------------------------------------------------


@router.post("/{asset_id}/finalize")
async def finalize_media(
    asset_id: uuid.UUID,
    owner_type: str = Query(...),
    owner_ref_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bind a staged media asset to a specific domain object (staged → ready)."""
    if owner_type not in ALLOWED_OWNER_TYPES:
        raise HTTPException(400, f"Unsupported owner_type: {owner_type}")

    result = await db.execute(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == user.id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    if asset.state != "staged":
        raise HTTPException(409, f"Cannot finalize asset in state '{asset.state}'")

    # Audit P1-3: the target domain object must exist and belong to this user.
    # Never trust an arbitrary owner_ref_id — a cross-user or non-existent
    # target would break integrity and future grant/publication rules.
    from app.services.media_registry import authorize_bind

    if not await authorize_bind(db, owner_type, owner_ref_id, user.id):
        raise HTTPException(404, "Target object not found or not owned by you")

    asset.state = "ready"
    asset.owner_type = owner_type
    asset.owner_ref_id = owner_ref_id
    # Auto-commit via get_db() after the endpoint (audit P1-5).
    await db.flush()
    await db.refresh(asset)
    return _serialize(asset)


# ---------------------------------------------------------------------------
# Serve (authorized)
# ---------------------------------------------------------------------------


@router.get("/{asset_id}")
async def serve_media(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Serve a media file. Only the owner may access it."""
    result = await db.execute(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == user.id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    if asset.state == "archived":
        raise HTTPException(410, "Media asset has been archived")

    path = asset.file_path.lstrip("/")
    import os

    full = os.path.join(os.getcwd(), path)
    if not os.path.isfile(full):
        raise HTTPException(404, "File not found on disk")
    return FileResponse(
        full,
        media_type=asset.mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{asset_id}/thumbnail")
async def serve_thumbnail(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Serve a media thumbnail."""
    result = await db.execute(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == user.id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    if not asset.thumbnail_path:
        raise HTTPException(404, "No thumbnail available")

    import os

    path = asset.thumbnail_path.lstrip("/")
    full = os.path.join(os.getcwd(), path)
    if not os.path.isfile(full):
        raise HTTPException(404, "Thumbnail not found on disk")
    return FileResponse(
        full,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store"},
    )


# ---------------------------------------------------------------------------
# Delete (owner-only, staged only)
# ---------------------------------------------------------------------------


@router.delete("/{asset_id}")
async def delete_media(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a media asset. Only staged (unbound) assets can be deleted."""
    result = await db.execute(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == user.id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(404, "Media asset not found")
    if asset.state != "staged":
        raise HTTPException(409, "Only staged assets can be deleted")

    file_path = asset.file_path
    thumb_path = asset.thumbnail_path
    await db.delete(asset)
    # Explicit commit here is intentional: the DB row must be durably removed
    # BEFORE the file is deleted from disk, so a failed commit keeps the file.
    await db.commit()
    delete_media_file(file_path, thumb_path)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("")
async def list_media(
    owner_type: str | None = Query(default=None),
    owner_ref_id: uuid.UUID | None = Query(default=None),
    state: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List user's media assets (paginated)."""
    stmt = select(MediaAsset).where(MediaAsset.owner_id == user.id)
    if owner_type:
        stmt = stmt.where(MediaAsset.owner_type == owner_type)
    if owner_ref_id:
        stmt = stmt.where(MediaAsset.owner_ref_id == owner_ref_id)
    if state:
        stmt = stmt.where(MediaAsset.state == state)
    stmt = stmt.order_by(MediaAsset.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return [_serialize(a) for a in result.scalars().all()]
