"""Social verification — requests, votes (S4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale
from app.models.user import User
from app.platform.social.repositories import (
    cast_vote,
    check_quorum_and_finalize,
    create_verification_policy,
    create_verification_request,
    get_profile,
    get_profile_by_alias,
    get_subject,
)
from app.templates_setup import templates

router = APIRouter(tags=["social"])


@router.get("/verification", response_class=HTMLResponse)
async def social_verification_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GET /social/verification — verification dashboard."""
    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)
    profile = await get_profile(db, current_user.id)
    if profile is None:
        return RedirectResponse(url="/social/profile", status_code=303)

    return templates.TemplateResponse(
        request,
        "social/verification.html",
        {"t": t, "locale": locale, "user": current_user, "profile": profile},
    )


@router.post("/verify/create", response_class=HTMLResponse)
async def social_verify_create(
    request: Request,
    subject_id: str = Form(...),
    min_approvals: int = Form(1),
    deadline_hours: int = Form(72),
    verifier_alias: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/verify/create — create a verification request."""
    subject_uuid = __import__("uuid").UUID(subject_id)
    subject = await get_subject(db, subject_uuid)
    if subject is None or subject.owner_id != current_user.id:
        raise HTTPException(404, "Subject not found")

    verifier_scope = {"type": "all_accepted"}
    if verifier_alias:
        target = await get_profile_by_alias(db, verifier_alias.strip().lower())
        if target:
            verifier_scope = {"type": "specific", "user_ids": [str(target.user_id)]}

    policy = await create_verification_policy(
        db,
        current_user.id,
        f"Verify {subject.subject_type}",
        verifier_scope,
        min_approvals=min_approvals,
        deadline_hours=deadline_hours,
    )
    await create_verification_request(db, policy.id, subject_uuid, current_user.id, deadline_hours)
    return RedirectResponse(url="/social/verification", status_code=303)


@router.post("/verify/{req_id}/vote", response_class=HTMLResponse)
async def social_verify_vote(
    req_id: str,
    value: str = Form(...),
    comment: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/verify/{id}/vote — cast a vote on a verification request."""
    if value not in ("approve", "reject", "abstain"):
        raise HTTPException(400, "Invalid vote value")

    req_uuid = __import__("uuid").UUID(req_id)
    vote = await cast_vote(db, req_uuid, current_user.id, value, comment)
    if vote is None:
        raise HTTPException(400, "Cannot vote — already voted, owner, or request closed")
    await check_quorum_and_finalize(db, req_uuid)
    return RedirectResponse(url="/social/verification", status_code=303)
