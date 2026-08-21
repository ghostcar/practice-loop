"""Dynamic Orchestration API (Revision 2 / Ports & Adapters / ADR-106).

Manages active operational modes and frozen rules snapshots.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.dynamic import DynamicDefinition
from app.models.user import User
from app.services.dynamic import (
    create_dynamic_definition,
    end_dynamic_run,
    get_active_dynamic_run,
    start_dynamic_run,
)
from app.templates_setup import templates

router = APIRouter(prefix="/dynamics", tags=["dynamics"])
json_router = APIRouter(prefix="/api/v2/dynamics", tags=["dynamics"])


@router.get("", response_class=HTMLResponse)
async def dynamics_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dynamic modes management dashboard."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    # Load definitions
    defs_res = await db.execute(
        select(DynamicDefinition)
        .where(DynamicDefinition.user_id == user.id)
        .order_by(DynamicDefinition.created_at.desc())
    )
    definitions = defs_res.scalars().all()

    # Load active run
    active_run = await get_active_dynamic_run(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="dynamics.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "dynamics",
            "definitions": definitions,
            "active_run": active_run,
        },
    )


@router.post("/new")
async def create_dynamic_endpoint(
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    agency_overlay_json: str = Form(default=""),
    included_protocols: str = Form(default=""),
    granted_capabilities: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new Dynamic mode blueprint."""
    overlay = {}
    if agency_overlay_json.strip():
        with contextlib.suppress(Exception):
            overlay = json.loads(agency_overlay_json.strip())

    protos = [x.strip() for x in included_protocols.split(",") if x.strip()]
    caps = [x.strip() for x in granted_capabilities.split(",") if x.strip()]

    await create_dynamic_definition(
        db=db,
        user_id=user.id,
        title=title.strip(),
        description=description.strip() or None,
        agency_overlay=overlay,
        included_protocol_ids=protos,
        granted_capabilities=caps,
    )
    await db.flush()

    referer = request.headers.get("referer", "/dynamics")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{dynamic_id}/start")
async def start_dynamic_endpoint(
    request: Request,
    dynamic_id: uuid.UUID,
    duration_days: int | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Launch a dynamic mode, freezing all rules into an immutable snapshot."""
    try:
        await start_dynamic_run(
            db=db,
            user_id=user.id,
            dynamic_id=dynamic_id,
            duration_days=duration_days,
        )
        await db.flush()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    referer = request.headers.get("referer", "/dynamics")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/runs/{run_id}/end")
async def end_dynamic_endpoint(
    request: Request,
    run_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Conclude an active dynamic run."""
    try:
        await end_dynamic_run(db=db, run_id=run_id)
        await db.flush()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    referer = request.headers.get("referer", "/dynamics")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (Mobile / Bearer clients)
# ─────────────────────────────────────────────────────────────────────────────


class DynamicDefinitionCreateRequest(BaseModel):
    title: str
    description: str | None = None
    agency_overlay: dict[str, Any] = Field(default_factory=dict)
    included_protocol_ids: list[str] = Field(default_factory=list)
    granted_capabilities: list[str] = Field(default_factory=list)


@json_router.get("")
async def get_dynamics_json(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List dynamic definitions and active run via JSON."""
    defs_res = await db.execute(select(DynamicDefinition).where(DynamicDefinition.user_id == user.id))
    active_run = await get_active_dynamic_run(db, user.id)
    return {
        "definitions": [
            {
                "id": str(d.id),
                "title": d.title,
                "description": d.description,
                "agency_overlay": d.agency_overlay,
            }
            for d in defs_res.scalars().all()
        ],
        "active_run": {
            "id": str(active_run.id),
            "status": active_run.status,
            "started_at": active_run.started_at.isoformat(),
            "expires_at": active_run.expires_at.isoformat() if active_run.expires_at else None,
            "frozen_snapshot": active_run.frozen_dynamic_snapshot,
        }
        if active_run
        else None,
    }
