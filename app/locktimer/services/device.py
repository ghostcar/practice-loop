"""LockTimer device helpers (Step 8, ADR-076).

A session can be bound to an optional physical device — an InventoryItem owned
by the same user (e.g. a chastity device, a padlock, a wearable). While a
session is active the device's operational ``inventory_status`` is ``in_use``;
on safety-stop/completion it returns to ``available``. The device itself is
metadata (not part of the canonical rules config — it does not affect the
schedule), so it is NOT frozen into LockSessionSnapshot.

Status transitions are best-effort: if the device was deleted (SET NULL) or
its status was manually changed by the user, we do not clobber manual state
beyond the session lifecycle.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.life import InventoryItem

IN_USE = "in_use"
AVAILABLE = "available"


async def get_device(db: AsyncSession, device_id: uuid.UUID, owner_id: uuid.UUID) -> InventoryItem | None:
    """Load a device owned by the user; None if missing/foreign/archived."""
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.id == device_id,
            InventoryItem.user_id == owner_id,
            InventoryItem.inventory_status != "archived",
        )
    )
    return result.scalar_one_or_none()


async def set_device_status(
    db: AsyncSession,
    device_id: uuid.UUID | None,
    owner_id: uuid.UUID,
    status: str,
) -> bool:
    """Set an owned device's operational status. Returns False if no device."""
    if device_id is None:
        return False
    device = await get_device(db, device_id, owner_id)
    if device is None:
        return False
    device.inventory_status = status
    db.add(device)
    await db.flush()
    return True
