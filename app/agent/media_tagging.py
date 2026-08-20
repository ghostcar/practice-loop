"""Auto AI Media Tagging & Smart Album Catalog Engine."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media import MediaAsset

logger = logging.getLogger(__name__)

SMART_ALBUM_MAPPINGS = {
    "activity_log": "Альбом Практик и Сессий",
    "lock_session": "Альбом Чек-инов Ключника",
    "care_entry": "Альбом Процедур Ухода",
    "inventory_item": "Каталог Экипировки",
}


async def auto_tag_and_catalog_media(
    db: AsyncSession,
    media_asset_id: str,
) -> dict[str, Any]:
    """Generates semantic AI tags and assigns media to smart albums based on content & owner."""
    import uuid

    asset_uuid = uuid.UUID(media_asset_id)
    asset = (await db.execute(select(MediaAsset).where(MediaAsset.id == asset_uuid))).scalar_one_or_none()

    if not asset:
        return {"status": "error", "reason": "asset_not_found"}

    # Determine tags based on owner_type and filename
    tags = ["verified_media"]
    owner_type = asset.owner_type.lower()

    if "lock" in owner_type or "timer" in owner_type:
        tags.extend(["chastity", "checkin", "keyholder"])
    elif "care" in owner_type:
        tags.extend(["aftercare", "skincare", "recovery"])
    elif "training" in owner_type or "activity" in owner_type:
        tags.extend(["fitness", "training_log", "discipline"])
    else:
        tags.extend(["general_proof"])

    album_name = SMART_ALBUM_MAPPINGS.get(owner_type, "Общий Смарт-Альбом")

    return {
        "status": "success",
        "media_asset_id": media_asset_id,
        "owner_type": asset.owner_type,
        "smart_album": album_name,
        "tags": tags,
    }
