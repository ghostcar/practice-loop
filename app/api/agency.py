"""Agency & Autonomy Policy API (Revision 2 / Ports & Adapters / ADR-106).

Manages user-defined autonomy policies and boundaries across domains and operations.
"""

from __future__ import annotations

import contextlib
import json
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
from app.models.agency import AgencyLevel, AgencyPolicy
from app.models.user import User
from app.services.agency import set_user_agency_policy
from app.templates_setup import templates

router = APIRouter(prefix="/agency", tags=["agency"])
json_router = APIRouter(prefix="/api/v2/agency", tags=["agency"])

ALL_DOMAINS = [
    "sessions",
    "training",
    "diet",
    "care",
    "medication",
    "protocols",
    "timer",
    "media",
    "insights",
]


# ─────────────────────────────────────────────────────────────────────────────
# HTML UI Pages & Forms
# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def agency_settings_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User autonomy and agency management dashboard."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    res = await db.execute(select(AgencyPolicy).where(AgencyPolicy.user_id == user.id))
    policies = {p.domain: p for p in res.scalars().all()}

    domains_data = []
    for d in ALL_DOMAINS:
        p = policies.get(d)
        domains_data.append(
            {
                "domain": d,
                "default_level": p.default_level if p else AgencyLevel.MANUAL.value,
                "operation_overrides": p.operation_overrides if p else {},
                "constraints": p.constraints if p else {},
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="agency.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "agency",
            "domains": domains_data,
            "agency_levels": [lvl.value for lvl in AgencyLevel],
        },
    )


@router.post("/{domain}")
async def update_domain_agency(
    request: Request,
    domain: str,
    default_level: str = Form(default=AgencyLevel.MANUAL.value),
    operation_overrides_json: str = Form(default=""),
    constraints_json: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save updated agency policy for domain."""
    if domain not in ALL_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Invalid domain '{domain}'")

    op_overrides = {}
    if operation_overrides_json.strip():
        with contextlib.suppress(Exception):
            op_overrides = json.loads(operation_overrides_json.strip())

    constraints = {}
    if constraints_json.strip():
        with contextlib.suppress(Exception):
            constraints = json.loads(constraints_json.strip())

    await set_user_agency_policy(
        db=db,
        user_id=user.id,
        domain=domain,
        default_level=default_level,
        operation_overrides=op_overrides,
        constraints=constraints,
    )
    await db.flush()

    referer = request.headers.get("referer", "/agency")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (Mobile / Bearer clients)
# ─────────────────────────────────────────────────────────────────────────────


class AgencyPolicyUpdateRequest(BaseModel):
    domain: str
    default_level: str = AgencyLevel.MANUAL.value
    operation_overrides: dict[str, str] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


@json_router.get("")
async def get_agency_policies_json(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all agency policies for current user."""
    res = await db.execute(select(AgencyPolicy).where(AgencyPolicy.user_id == user.id))
    policies = res.scalars().all()
    return {
        "user_id": str(user.id),
        "policies": [
            {
                "domain": p.domain,
                "default_level": p.default_level,
                "operation_overrides": p.operation_overrides,
                "constraints": p.constraints,
            }
            for p in policies
        ],
    }


@json_router.post("")
async def set_agency_policy_json(
    req: AgencyPolicyUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update agency policy via JSON."""
    policy = await set_user_agency_policy(
        db=db,
        user_id=user.id,
        domain=req.domain,
        default_level=req.default_level,
        operation_overrides=req.operation_overrides,
        constraints=req.constraints,
    )
    await db.flush()
    return {
        "status": "success",
        "domain": policy.domain,
        "default_level": policy.default_level,
    }
