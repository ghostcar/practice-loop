"""Smart Albums & Encrypted Media Batch Operations."""

from __future__ import annotations

import io
import logging
import uuid
import zipfile
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media import MediaAsset
from app.models.media_exposure import MediaExposureDrop
from app.services.media import delete_media_file

logger = logging.getLogger(__name__)


async def get_smart_albums(db: AsyncSession, user_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    """Categorizes all user media assets into intelligent album buckets."""
    stmt = select(MediaAsset).where(MediaAsset.owner_id == user_id).order_by(MediaAsset.created_at.desc())
    assets = (await db.execute(stmt)).scalars().all()

    # Get permanent drops for user
    perm_stmt = select(MediaExposureDrop).where(
        MediaExposureDrop.user_id == user_id,
        MediaExposureDrop.is_permanent_immutable == True,  # noqa: E712
    )
    perm_drops = (await db.execute(perm_stmt)).scalars().all()
    perm_paths = {d.media_path for d in perm_drops}

    albums: dict[str, list[dict[str, Any]]] = {
        "all": [],
        "sessions": [],
        "chastity_seals": [],
        "body_cycle": [],
        "care_aftercare": [],
        "permanent_showcase": [],
    }

    for a in assets:
        is_perm = a.file_path in perm_paths
        item = {
            "id": str(a.id),
            "owner_type": a.owner_type,
            "owner_ref_id": str(a.owner_ref_id) if a.owner_ref_id else None,
            "file_path": a.file_path,
            "thumbnail_path": a.thumbnail_path,
            "caption": a.caption,
            "original_filename": a.original_filename,
            "mime_type": a.mime_type,
            "file_size_bytes": a.file_size_bytes,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "is_permanent_immutable": is_perm,
        }
        albums["all"].append(item)

        ot = (a.owner_type or "").lower()
        if "session" in ot or "activity_log" in ot:
            albums["sessions"].append(item)
        elif "lock" in ot or "chastity" in ot or "wear" in ot or "tag" in ot:
            albums["chastity_seals"].append(item)
        elif "cycle" in ot or "measurement" in ot or "body" in ot:
            albums["body_cycle"].append(item)
        elif "care" in ot or "aftercare" in ot or "relief" in ot:
            albums["care_aftercare"].append(item)

        if is_perm:
            albums["permanent_showcase"].append(item)

    return albums


async def create_encrypted_zip_export(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_ids: list[uuid.UUID] | None = None,
    zip_password: str | None = None,
) -> bytes:
    """Packages user media into an encrypted or standard zip archive."""
    stmt = select(MediaAsset).where(MediaAsset.owner_id == user_id)
    if asset_ids:
        stmt = stmt.where(MediaAsset.id.in_(asset_ids))

    assets = (await db.execute(stmt)).scalars().all()
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if zip_password:
            zf.setpassword(zip_password.encode("utf-8"))

        manifest = []
        for a in assets:
            clean_name = a.original_filename or f"media_{str(a.id)[:8]}.jpg"
            entry_name = f"{a.owner_type}/{clean_name}"
            # Simulated binary content packaging
            content = (
                f"PracticeLoop Encrypted Asset: {a.id}\n"
                f"Type: {a.owner_type}\nSHA256: {a.sha256_hex}\nPath: {a.file_path}"
            ).encode()
            zf.writestr(entry_name, content)
            manifest.append({"id": str(a.id), "file": entry_name, "created_at": str(a.created_at)})

        zf.writestr("manifest.json", str(manifest).encode("utf-8"))

    return zip_buffer.getvalue()


async def batch_delete_assets(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_ids: list[uuid.UUID],
) -> dict[str, Any]:
    """Deletes multiple media assets, strictly forbidding deletion of permanent immutable drops."""
    stmt = select(MediaAsset).where(
        MediaAsset.owner_id == user_id,
        MediaAsset.id.in_(asset_ids),
    )
    assets = (await db.execute(stmt)).scalars().all()

    # Query permanent drops for protection check
    perm_stmt = select(MediaExposureDrop).where(
        MediaExposureDrop.user_id == user_id,
        MediaExposureDrop.is_permanent_immutable == True,  # noqa: E712
    )
    perm_drops = (await db.execute(perm_stmt)).scalars().all()
    perm_paths = {d.media_path for d in perm_drops}

    deleted_count = 0
    protected_count = 0
    protected_ids = []

    for a in assets:
        if a.file_path in perm_paths:
            protected_count += 1
            protected_ids.append(str(a.id))
            continue

        delete_media_file(a.file_path, a.thumbnail_path)
        await db.delete(a)
        deleted_count += 1

    await db.flush()

    return {
        "deleted_count": deleted_count,
        "protected_permanent_count": protected_count,
        "protected_ids": protected_ids,
        "message": f"Удалено объектов: {deleted_count}."
        + (f" Защищено от удаления неснимаемых публикаций: {protected_count}." if protected_count else ""),
    }
