"""Chastity device care API (B2, PRODUCT_OVERVIEW §6.2).

Журнал ухода за физическим устройством во время ношения: комфорт, проблемы,
обслуживание, очистка, осмотр. Relief-only (PD-013) — без игровой интеграции.

JSON API (мобильный/bearer):
- GET  /api/v2/devices/events      — список (фильтр по device_id/session_id)
- POST /api/v2/devices/events      — создать запись (201)
- DELETE /api/v2/devices/events/{id} — удалить (204)

Form (HTMX):
- POST /device-events              — создать запись → redirect
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.device import DEVICE_EVENT_TYPES, DEVICE_SEVERITIES, ChastityDeviceEvent
from app.models.user import User

router = APIRouter(tags=["device"])
json_router = APIRouter(prefix="/api/v2/devices", tags=["device"])


def _event_dict(e: ChastityDeviceEvent) -> dict:
    return {
        "id": str(e.id),
        "device_id": str(e.device_id) if e.device_id else None,
        "session_id": str(e.session_id) if e.session_id else None,
        "event_type": e.event_type,
        "comfort_level": e.comfort_level,
        "severity": e.severity,
        "notes": e.notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _validate_payload(
    event_type: str,
    comfort_level: int | None,
    severity: str | None,
) -> None:
    if event_type not in DEVICE_EVENT_TYPES:
        raise HTTPException(400, "Invalid event_type")
    if comfort_level is not None and not (1 <= comfort_level <= 5):
        raise HTTPException(400, "comfort_level must be 1-5")
    if severity is not None and severity not in DEVICE_SEVERITIES:
        raise HTTPException(400, "Invalid severity")


# ─────────────────────────────────────────────────────────────────────────────
# Form handler (HTMX)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/device-events")
async def add_device_event_form(
    request: Request,
    event_type: str = Form(...),
    device_id: str = Form(default=""),
    session_id: str = Form(default=""),
    comfort_level: str = Form(default=""),
    severity: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    comfort = int(comfort_level) if comfort_level.strip().isdigit() else None
    sev = (severity or "").strip() or None
    _validate_payload(event_type, comfort, sev)

    dev_id = uuid.UUID(device_id) if device_id.strip() else None
    sess_id = uuid.UUID(session_id) if session_id.strip() else None

    # owner-scoped device validation (soft link)
    if dev_id is not None:
        from app.locktimer.services.device import get_device

        if await get_device(db, dev_id, user.id) is None:
            raise HTTPException(400, "Device not found")

    ev = ChastityDeviceEvent(
        user_id=user.id,
        device_id=dev_id,
        session_id=sess_id,
        event_type=event_type,
        comfort_level=comfort,
        severity=sev,
        notes=(notes or "").strip() or None,
    )
    db.add(ev)
    await db.flush()
    back = request.headers.get("referer") or "/locktimer"
    return RedirectResponse(url=back, status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("/events")
async def json_list_events(
    device_id: uuid.UUID | None = Query(None),
    session_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(ChastityDeviceEvent).where(ChastityDeviceEvent.user_id == user.id)
    if device_id is not None:
        query = query.where(ChastityDeviceEvent.device_id == device_id)
    if session_id is not None:
        query = query.where(ChastityDeviceEvent.session_id == session_id)
    rows = (await db.execute(query.order_by(ChastityDeviceEvent.created_at.desc()))).scalars().all()
    return [_event_dict(e) for e in rows]


class DeviceEventBody(BaseModel):
    event_type: str
    device_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    comfort_level: int | None = Field(default=None, ge=1, le=5)
    severity: str | None = None
    notes: str | None = None


@json_router.post("/events", status_code=201)
async def json_add_event(
    body: DeviceEventBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_payload(body.event_type, body.comfort_level, body.severity)

    if body.device_id is not None:
        from app.locktimer.services.device import get_device

        if await get_device(db, body.device_id, user.id) is None:
            raise HTTPException(400, "Device not found")

    ev = ChastityDeviceEvent(
        user_id=user.id,
        device_id=body.device_id,
        session_id=body.session_id,
        event_type=body.event_type,
        comfort_level=body.comfort_level,
        severity=body.severity,
        notes=(body.notes or "").strip() or None,
    )
    db.add(ev)
    await db.flush()
    return _event_dict(ev)


@json_router.delete("/events/{event_id}", status_code=204)
async def json_delete_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ev = (
        await db.execute(
            select(ChastityDeviceEvent).where(
                ChastityDeviceEvent.id == event_id, ChastityDeviceEvent.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if ev is None:
        raise HTTPException(404, "Device event not found")
    await db.delete(ev)
    await db.flush()
    return None
