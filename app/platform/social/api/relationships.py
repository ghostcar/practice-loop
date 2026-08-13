"""Social relationships — invites, blocks, grants, notifications (S2)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale
from app.models.user import User
from app.platform.social.repositories import (
    _is_blocked,
    accept_grant,
    accept_invitation,
    block_user,
    create_grant,
    create_invitation,
    create_notification,
    decline_invitation,
    get_profile,
    get_profile_by_alias,
    get_relationship,
    get_relationship_by_pair,
    list_grants_for_relationship,
    list_notifications,
    list_pending_invitations,
    list_user_blocks,
    list_user_relationships,
    mark_notification_read,
    revoke_grant,
    revoke_relationship,
    unblock_user,
)
from app.templates_setup import templates
from app.timeutils import as_utc

router = APIRouter(tags=["social"])


@router.get("/relationships", response_class=HTMLResponse)
async def social_relationships_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GET /social/relationships — view relationships, invites, blocks, grants."""
    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)
    profile = await get_profile(db, current_user.id)

    if profile is None:
        return RedirectResponse(url="/social/profile", status_code=303)

    relationships = await list_user_relationships(db, current_user.id)
    pending_invites = await list_pending_invitations(db, current_user.id)
    blocks = await list_user_blocks(db, current_user.id)
    notifications = await list_notifications(db, current_user.id, limit=20)

    # Enrich: attach grants to each relationship
    rel_data = []
    for rel in relationships:
        grants = await list_grants_for_relationship(db, rel.id)
        other_id = rel.requester_id if rel.recipient_id == current_user.id else rel.recipient_id
        other_profile = await get_profile(db, other_id)
        rel_data.append(
            {
                "rel": rel,
                "grants": grants,
                "other_alias": other_profile.alias if other_profile else "unknown",
            }
        )

    # Enrich blocks with alias
    block_data = []
    for blk in blocks:
        blocked_profile = await get_profile(db, blk.blocked_id)
        block_data.append(
            {
                "block": blk,
                "blocked_alias": blocked_profile.alias if blocked_profile else "unknown",
            }
        )

    # Enrich pending invites with requester alias
    invite_data = []
    for inv in pending_invites:
        requester_profile = await get_profile(db, inv.requester_id)
        invite_data.append(
            {
                "invite": inv,
                "requester_alias": requester_profile.alias if requester_profile else "unknown",
            }
        )

    return templates.TemplateResponse(
        request,
        "social/relationships.html",
        {
            "t": t,
            "locale": locale,
            "user": current_user,
            "profile": profile,
            "relationships": rel_data,
            "pending_invites": invite_data,
            "blocks": block_data,
            "notifications": notifications,
        },
    )


@router.post("/invite", response_class=HTMLResponse)
async def social_invite_send(
    request: Request,
    alias: str = Form(min_length=3, max_length=80),
    display_role: str = Form("viewer"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/invite — send invitation to another user by alias."""

    if display_role not in ("viewer", "coach", "mentor", "curator"):
        raise HTTPException(400, "Invalid role preset")

    recipient_profile = await get_profile_by_alias(db, alias.strip().lower())
    if recipient_profile is None:
        raise HTTPException(400, "User not found by alias")
    if recipient_profile.user_id == current_user.id:
        raise HTTPException(400, "Cannot invite yourself")

    # Check block
    if await _is_blocked(db, current_user.id, recipient_profile.user_id):
        raise HTTPException(403, "Cannot invite — blocked")

    # Check existing relationship
    existing = await get_relationship_by_pair(db, current_user.id, recipient_profile.user_id)
    if existing is not None:
        if existing.status in ("accepted",):
            raise HTTPException(409, "Already connected")
        if existing.status == "pending":
            raise HTTPException(409, "Invitation already pending")
        # declined/expired/revoked — check cooldown
        cooldown = existing.cooldown_until
        if cooldown is not None:
            cooldown = as_utc(cooldown)
            if cooldown > datetime.now(UTC):
                raise HTTPException(409, "Cooldown active — try later")

    rel = await create_invitation(db, current_user.id, recipient_profile.user_id, display_role)
    await create_notification(
        db,
        recipient_profile.user_id,
        "invitation_received",
        {"relationship_id": str(rel.id), "requester_alias": (await get_profile(db, current_user.id)).alias},
    )
    return RedirectResponse(url="/social/relationships", status_code=303)


@router.post("/invite/{rel_id}/accept", response_class=HTMLResponse)
async def social_invite_accept(
    rel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/invite/{id}/accept — accept a pending invitation."""
    rel_uuid = __import__("uuid").UUID(rel_id)
    rel = await accept_invitation(db, rel_uuid, current_user.id)
    if rel is None:
        raise HTTPException(404, "Invitation not found or not pending")
    await create_notification(
        db,
        rel.requester_id,
        "invitation_accepted",
        {"relationship_id": str(rel.id)},
    )
    return RedirectResponse(url="/social/relationships", status_code=303)


@router.post("/invite/{rel_id}/decline", response_class=HTMLResponse)
async def social_invite_decline(
    rel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/invite/{id}/decline — decline a pending invitation."""
    rel_uuid = __import__("uuid").UUID(rel_id)
    rel = await decline_invitation(db, rel_uuid, current_user.id)
    if rel is None:
        raise HTTPException(404, "Invitation not found or not pending")
    await create_notification(
        db,
        rel.requester_id,
        "invitation_declined",
        {"relationship_id": str(rel.id)},
    )
    return RedirectResponse(url="/social/relationships", status_code=303)


@router.post("/invite/{rel_id}/revoke", response_class=HTMLResponse)
async def social_invite_revoke(
    rel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/invite/{id}/revoke — revoke any active relationship."""
    rel_uuid = __import__("uuid").UUID(rel_id)
    rel = await revoke_relationship(db, rel_uuid, current_user.id)
    if rel is None:
        raise HTTPException(404, "Relationship not found")
    other_id = rel.requester_id if rel.recipient_id == current_user.id else rel.recipient_id
    await create_notification(
        db,
        other_id,
        "relationship_revoked",
        {"relationship_id": str(rel.id)},
    )
    return RedirectResponse(url="/social/relationships", status_code=303)


@router.post("/block", response_class=HTMLResponse)
async def social_block_user(
    request: Request,
    alias: str = Form(min_length=3, max_length=80),
    reason: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/block — block another user by alias."""
    target_profile = await get_profile_by_alias(db, alias.strip().lower())
    if target_profile is None:
        raise HTTPException(400, "User not found by alias")
    if target_profile.user_id == current_user.id:
        raise HTTPException(400, "Cannot block yourself")

    # Check existing block
    existing = await get_relationship_by_pair(db, current_user.id, target_profile.user_id)
    if existing is not None:
        pass  # block supersedes relationship

    await block_user(db, current_user.id, target_profile.user_id, reason)
    return RedirectResponse(url="/social/relationships", status_code=303)


@router.post("/block/{block_id}/remove", response_class=HTMLResponse)
async def social_unblock_user(
    block_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/block/{id}/remove — remove a block."""
    import uuid as _uuid

    await unblock_user(db, current_user.id, _uuid.UUID(block_id))
    return RedirectResponse(url="/social/relationships", status_code=303)


@router.post("/grant", response_class=HTMLResponse)
async def social_grant_create(
    request: Request,
    relationship_id: str = Form(...),
    scope_type: str = Form("subject"),
    caps_json: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/grant — propose a capability grant."""
    import json as _json

    rel_uuid = __import__("uuid").UUID(relationship_id)
    rel = await get_relationship(db, rel_uuid)
    if rel is None or rel.requester_id != current_user.id:
        raise HTTPException(404, "Relationship not found")
    if rel.status != "accepted":
        raise HTTPException(400, "Relationship must be accepted first")

    try:
        caps = _json.loads(caps_json)
    except _json.JSONDecodeError:
        raise HTTPException(400, "Invalid caps JSON") from None

    grant = await create_grant(db, rel_uuid, scope_type, caps)
    await create_notification(
        db,
        rel.recipient_id,
        "grant_proposed",
        {"grant_id": str(grant.id), "relationship_id": str(rel.id)},
    )
    return RedirectResponse(url="/social/relationships", status_code=303)


@router.post("/grant/{grant_id}/accept", response_class=HTMLResponse)
async def social_grant_accept(
    grant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/grant/{id}/accept — accept a proposed grant."""
    grant_uuid = __import__("uuid").UUID(grant_id)
    grant = await accept_grant(db, grant_uuid, current_user.id)
    if grant is None:
        raise HTTPException(404, "Grant not found or not proposable")
    return RedirectResponse(url="/social/relationships", status_code=303)


@router.post("/grant/{grant_id}/revoke", response_class=HTMLResponse)
async def social_grant_revoke(
    grant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/grant/{id}/revoke — revoke a grant (either party)."""
    grant_uuid = __import__("uuid").UUID(grant_id)
    grant = await revoke_grant(db, grant_uuid, current_user.id)
    if grant is None:
        raise HTTPException(404, "Grant not found")
    return RedirectResponse(url="/social/relationships", status_code=303)


@router.post("/notifications/{notif_id}/read", response_class=HTMLResponse)
async def social_notification_read(
    notif_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/notifications/{id}/read — mark notification as read."""
    import uuid as _uuid

    await mark_notification_read(db, _uuid.UUID(notif_id), current_user.id)
    return RedirectResponse(url="/social/relationships", status_code=303)
