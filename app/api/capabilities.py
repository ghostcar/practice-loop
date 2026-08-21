"""Capability Grants API (Revision 2 / Ports & Adapters / ADR-106).

Manages granular actor-to-actor capability delegations across D/s, Social, and Protocols.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.capability import CapabilityGrantV2
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(prefix="/capabilities", tags=["capabilities"])
json_router = APIRouter(prefix="/api/v2/capabilities", tags=["capabilities"])


@router.get("", response_class=HTMLResponse)
async def capabilities_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Capabilities management dashboard: issued and received grants."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    now = datetime.datetime.now(datetime.UTC)

    # Grants issued by current user
    issued_res = await db.execute(
        select(CapabilityGrantV2)
        .where(CapabilityGrantV2.issuer_id == user.id)
        .order_by(CapabilityGrantV2.created_at.desc())
    )
    issued_grants = issued_res.scalars().all()

    # Grants received by current user
    received_res = await db.execute(
        select(CapabilityGrantV2)
        .where(CapabilityGrantV2.recipient_id == user.id)
        .order_by(CapabilityGrantV2.created_at.desc())
    )
    received_grants = received_res.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="capabilities.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "capabilities",
            "issued_grants": issued_grants,
            "received_grants": received_grants,
            "now": now,
        },
    )


@router.post("")
async def create_capability_grant(
    request: Request,
    recipient_email: str = Form(...),
    capability_code: str = Form(...),
    resource_scope_json: str = Form(default=""),
    constraints_json: str = Form(default=""),
    duration_days: int | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Issue a new capability grant to another user."""
    # Find recipient by email
    res = await db.execute(select(User).where(User.email == recipient_email.strip()))
    recipient = res.scalar_one_or_none()
    if recipient is None:
        raise HTTPException(status_code=404, detail="Recipient user not found")

    scope = {}
    if resource_scope_json.strip():
        with contextlib.suppress(Exception):
            scope = json.loads(resource_scope_json.strip())

    constraints = {}
    if constraints_json.strip():
        with contextlib.suppress(Exception):
            constraints = json.loads(constraints_json.strip())

    valid_until = None
    if duration_days:
        valid_until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=duration_days)

    grant = CapabilityGrantV2(
        issuer_id=user.id,
        recipient_id=recipient.id,
        capability_code=capability_code.strip(),
        resource_scope=scope,
        constraints=constraints,
        valid_until=valid_until,
        status="active",
    )
    db.add(grant)
    await db.flush()

    referer = request.headers.get("referer", "/capabilities")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{grant_id}/revoke")
async def revoke_capability_grant(
    request: Request,
    grant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an issued or received capability grant."""
    res = await db.execute(
        select(CapabilityGrantV2).where(
            CapabilityGrantV2.id == grant_id,
            or_(CapabilityGrantV2.issuer_id == user.id, CapabilityGrantV2.recipient_id == user.id),
        )
    )
    grant = res.scalar_one_or_none()
    if grant is None:
        raise HTTPException(status_code=404, detail="Grant not found")

    grant.status = "revoked"
    await db.flush()

    referer = request.headers.get("referer", "/capabilities")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (Mobile / Bearer clients)
# ─────────────────────────────────────────────────────────────────────────────


class CapabilityGrantCreateRequest(BaseModel):
    recipient_id: uuid.UUID
    capability_code: str
    resource_scope: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    duration_days: int | None = None


@json_router.get("")
async def get_capabilities_json(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active capability grants for current user."""
    res = await db.execute(
        select(CapabilityGrantV2).where(
            or_(CapabilityGrantV2.issuer_id == user.id, CapabilityGrantV2.recipient_id == user.id)
        )
    )
    grants = res.scalars().all()
    return {
        "user_id": str(user.id),
        "grants": [
            {
                "id": str(g.id),
                "issuer_id": str(g.issuer_id),
                "recipient_id": str(g.recipient_id),
                "capability_code": g.capability_code,
                "status": g.status,
                "valid_until": g.valid_until.isoformat() if g.valid_until else None,
            }
            for g in grants
        ],
    }


@json_router.post("")
async def create_capability_json(
    req: CapabilityGrantCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Issue capability grant via JSON API."""
    valid_until = None
    if req.duration_days:
        valid_until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=req.duration_days)

    grant = CapabilityGrantV2(
        issuer_id=user.id,
        recipient_id=req.recipient_id,
        capability_code=req.capability_code,
        resource_scope=req.resource_scope,
        constraints=req.constraints,
        valid_until=valid_until,
        status="active",
    )
    db.add(grant)
    await db.flush()
    return {"status": "success", "grant_id": str(grant.id)}
