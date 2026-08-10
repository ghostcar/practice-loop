"""Generic photo attachments — photo reports for any section.

owner_type keys: activity_log / training_day / inventory_item / diet / measurement.
The endpoint is intentionally owner-agnostic: the caller passes owner_type+owner_id
and the attachment is bound to the current user. Ownership re-checks happen per
section when the page renders them.
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.attachment import Attachment
from app.models.user import User
from app.services.uploads import delete_upload, save_image

router = APIRouter(prefix="/attachments", tags=["attachments"])

# Allowlist of owner types (audit: prevents arbitrary owner_type strings).
OWNER_TYPES = {"activity_log", "training_day", "inventory_item", "diet", "measurement", "training_log_entry"}


def _serialize(a: Attachment) -> dict:
    return {
        "id": str(a.id),
        "owner_type": a.owner_type,
        "owner_id": str(a.owner_id),
        "file_path": a.file_path,
        "caption": a.caption,
        "sort_order": a.sort_order,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("")
async def upload_attachment(
    owner_type: str = Query(...),
    owner_id: uuid.UUID = Query(...),
    file: UploadFile = File(...),
    caption: str | None = Query(default=None, max_length=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a photo report attached to a domain object."""
    if owner_type not in OWNER_TYPES:
        raise HTTPException(400, f"Unsupported owner_type: {owner_type}")
    url = await save_image(file, subdir="attachments")
    # Append after existing ones.
    result = await db.execute(
        select(Attachment).where(
            Attachment.user_id == user.id,
            Attachment.owner_type == owner_type,
            Attachment.owner_id == owner_id,
        )
    )
    existing = list(result.scalars().all())
    next_order = max((a.sort_order for a in existing), default=-1) + 1

    att = Attachment(
        user_id=user.id,
        owner_type=owner_type,
        owner_id=owner_id,
        file_path=url,
        caption=(caption or "").strip()[:500] or None,
        sort_order=next_order,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    return _serialize(att)


@router.get("")
async def list_attachments(
    owner_type: str = Query(...),
    owner_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List attachments for a domain object (current user only)."""
    if owner_type not in OWNER_TYPES:
        raise HTTPException(400, f"Unsupported owner_type: {owner_type}")
    result = await db.execute(
        select(Attachment)
        .where(
            Attachment.user_id == user.id,
            Attachment.owner_type == owner_type,
            Attachment.owner_id == owner_id,
        )
        .order_by(Attachment.sort_order, Attachment.created_at)
    )
    return [_serialize(a) for a in result.scalars().all()]


@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete an attachment (owner only) and its file from disk."""
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id, Attachment.user_id == user.id))
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(404, "Attachment not found")
    path = att.file_path
    await db.delete(att)
    await db.commit()
    delete_upload(path)
    return {"status": "deleted"}
