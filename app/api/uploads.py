"""Authorized upload serving — replaces the public ``/uploads`` static mount.

Audit P0-1: user media (attachments, inventory photos, universal media) was
served through a public ``StaticFiles`` mount, bypassing ownership checks.
This router serves the same ``/uploads/<subdir>/<name>`` URLs but requires an
authenticated session and verifies that the current user owns the file.

Ownership is resolved by reverse lookup against the tables that store upload
paths:

- ``Attachment.file_path`` (photo reports);
- ``InventoryItem.image_path`` (inventory photos);
- ``MediaAsset.file_path`` / ``MediaAsset.thumbnail_path`` (universal media).

An unauthenticated request, a cross-user URL, a non-existent path, or any path
escaping the upload directory returns 404 (no existence leak).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User

router = APIRouter()

_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _mime_for(url: str) -> str:
    suffix = Path(url).suffix.lower()
    return _MIME_BY_EXT.get(suffix, "application/octet-stream")


def resolve_upload_path(base: Path, path: str) -> Path | None:
    """Resolve a relative upload path inside ``base``, or None if it escapes."""
    if not path or path.startswith("/") or "\\" in path:
        return None
    candidate = (base / path).resolve()
    if not str(candidate).startswith(str(base) + "/") and candidate != base:
        return None
    return candidate


async def _is_owned(db: AsyncSession, url: str, user_id: object) -> bool:
    """True if the current user owns an upload stored under this URL path."""
    from app.models.attachment import Attachment
    from app.models.life import InventoryItem
    from app.models.media import MediaAsset

    r = await db.execute(
        select(Attachment.id).where(Attachment.file_path == url, Attachment.user_id == user_id).limit(1)
    )
    if r.first():
        return True

    r = await db.execute(
        select(InventoryItem.id).where(InventoryItem.image_path == url, InventoryItem.user_id == user_id).limit(1)
    )
    if r.first():
        return True

    r = await db.execute(
        select(MediaAsset.id)
        .where(
            or_(MediaAsset.file_path == url, MediaAsset.thumbnail_path == url),
            MediaAsset.owner_id == user_id,
        )
        .limit(1)
    )
    return r.first() is not None


@router.get("/uploads/{path:path}")
async def serve_upload(
    path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Serve an uploaded file to its owner only (audit P0-1)."""
    base = Path(settings.upload_dir).resolve()
    # Hard containment check: the resolved file must stay inside the upload dir.
    candidate = resolve_upload_path(base, path)
    if candidate is None or not candidate.is_file():
        raise HTTPException(404, "Not found")

    url = "/uploads/" + path
    if not await _is_owned(db, url, user.id):
        raise HTTPException(404, "Not found")

    return FileResponse(
        candidate,
        media_type=_mime_for(url),
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
