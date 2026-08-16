"""Push device registration API (Mobile Foundation, M4).

JSON-first (bearer or cookie). Registers device tokens that the notification
flow later dispatches push messages to via ``app.push.dispatch_push``.

POST   /api/v2/push/devices                 — register/upsert a device token
GET    /api/v2/push/devices                 — list the caller's devices
POST   /api/v2/push/devices/{id}/deactivate — deactivate a device
DELETE /api/v2/push/devices/{id}            — remove a device
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.push_device import PushDevice
from app.models.user import User

router = APIRouter(prefix="/api/v2/push", tags=["push-devices"])

ALLOWED_PLATFORMS = {"fcm_android", "apns_ios", "web", "other"}


class DeviceRegister(BaseModel):
    platform: str = Field(min_length=1, max_length=30)
    device_token: str = Field(min_length=1, max_length=512)
    app_version: str | None = Field(default=None, max_length=50)


def _serialize(d: PushDevice) -> dict:
    return {
        "id": str(d.id),
        "platform": d.platform,
        "device_token": d.device_token,
        "app_version": d.app_version,
        "is_active": d.is_active,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


@router.post("/devices", status_code=201)
async def register_device(
    body: DeviceRegister,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register (or re-activate) a push device token for the caller."""
    platform = body.platform.strip().lower()
    if platform not in ALLOWED_PLATFORMS:
        raise HTTPException(400, f"Unsupported platform: {body.platform}")

    result = await db.execute(
        select(PushDevice).where(
            PushDevice.user_id == user.id,
            PushDevice.platform == platform,
            PushDevice.device_token == body.device_token,
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        device = PushDevice(
            user_id=user.id,
            platform=platform,
            device_token=body.device_token,
            app_version=body.app_version,
            last_seen_at=datetime.now(UTC),
        )
        db.add(device)
    else:
        device.is_active = True
        device.app_version = body.app_version or device.app_version
        device.last_seen_at = datetime.now(UTC)
        db.add(device)
    await db.flush()
    return _serialize(device)


@router.get("/devices")
async def list_devices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PushDevice).where(PushDevice.user_id == user.id).order_by(PushDevice.created_at.desc())
    )
    return [_serialize(d) for d in result.scalars().all()]


@router.post("/devices/{device_id}/deactivate")
async def deactivate_device(
    device_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PushDevice).where(PushDevice.id == device_id, PushDevice.user_id == user.id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(404, "Device not found")
    device.is_active = False
    db.add(device)
    await db.flush()
    return {"status": "deactivated", "id": str(device.id)}


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PushDevice).where(PushDevice.id == device_id, PushDevice.user_id == user.id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(404, "Device not found")
    await db.delete(device)
    await db.flush()
    return {"status": "deleted", "id": str(device_id)}
