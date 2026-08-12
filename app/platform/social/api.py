"""Platform Social — API routes (11_SOCIAL_SPEC.md, 12_SOCIAL_IMPLEMENTATION_PLAN.md S0).

Registered only when composition.social_operational is True.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale
from app.models.user import User
from app.platform.social import get_adapter_registry
from app.platform.social.models import SocialProfile
from app.platform.social.repositories import (
    _is_blocked,
    accept_grant,
    accept_invitation,
    assign_report,
    block_user,
    cast_vote,
    check_quorum_and_finalize,
    create_comment,
    create_encouragement,
    create_grant,
    create_invitation,
    create_moderation_action,
    create_notification,
    create_profile,
    create_publication,
    create_report,
    create_verification_policy,
    create_verification_request,
    decline_invitation,
    delete_comment,
    dismiss_report,
    edit_comment,
    get_profile,
    get_profile_by_alias,
    get_publication,
    get_relationship,
    get_relationship_by_pair,
    get_report,
    get_subject,
    has_accepted_consent,
    hide_comment,
    hide_publication,
    invalidate_vote,
    list_feed,
    list_grants_for_relationship,
    list_moderation_actions,
    list_notifications,
    list_owner_publications,
    list_owner_subjects,
    list_pending_invitations,
    list_reports,
    list_user_blocks,
    list_user_relationships,
    mark_notification_read,
    record_consent,
    resolve_report,
    revoke_grant,
    revoke_relationship,
    unblock_user,
    update_profile,
    withdraw_publication,
)
from app.templates_setup import templates

router = APIRouter(prefix="/social", tags=["social"])

CURRENT_CONSENT_VERSION = 1


# ---------------------------------------------------------------------------
# S0 — Profile pages
# ---------------------------------------------------------------------------


async def _check_social_access(
    db: AsyncSession,
    user: User,
    require_consent: bool = True,
) -> tuple[SocialProfile | None, str]:
    """Verify social is accessible: profile exists + consent accepted."""
    profile = await get_profile(db, user.id)
    if profile is None:
        return None, "profile_not_created"
    if require_consent and not await has_accepted_consent(db, user.id, CURRENT_CONSENT_VERSION):
        return profile, "consent_required"
    return profile, "ok"


@router.get("/profile", response_class=HTMLResponse)
async def social_profile_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GET /social/profile — view/edit your social profile."""
    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)
    profile = await get_profile(db, current_user.id)

    return templates.TemplateResponse(
        request,
        "social/profile.html",
        {
            "t": t,
            "locale": locale,
            "user": current_user,
            "profile": profile,
            "consent_accepted": await has_accepted_consent(db, current_user.id, CURRENT_CONSENT_VERSION),
            "consent_version": CURRENT_CONSENT_VERSION,
        },
    )


@router.post("/profile/create", response_class=HTMLResponse)
async def social_profile_create(
    request: Request,
    alias: str = Form(min_length=3, max_length=80),
    bio: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/profile/create — create social profile with alias."""

    # Validate alias — ASCII alphanumeric + underscore + hyphen only
    alias_stripped = alias.strip()
    if not alias_stripped:
        raise HTTPException(400, "Alias cannot be empty")
    for ch in alias_stripped:
        if not (ch.isascii() and (ch.isalnum() or ch in "_-")):
            raise HTTPException(400, "Alias must be alphanumeric, underscore, or hyphen")
    alias_normalized = alias_stripped.lower()

    # Check uniqueness
    existing = await get_profile_by_alias(db, alias_normalized)
    if existing is not None:
        raise HTTPException(409, "Alias already taken")

    # Check if user already has a profile
    if await get_profile(db, current_user.id) is not None:
        raise HTTPException(409, "Profile already exists")

    await create_profile(db, current_user.id, alias_stripped, alias_normalized, bio)

    return RedirectResponse(url="/social/profile", status_code=303)


@router.post("/profile/update", response_class=HTMLResponse)
async def social_profile_update(
    request: Request,
    bio: str | None = Form(None),
    discoverable: bool | None = Form(None),
    show_in_feed: bool | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/profile/update — update profile fields."""
    await update_profile(db, current_user.id, bio=bio, discoverable=discoverable, show_in_feed=show_in_feed)
    return RedirectResponse(url="/social/profile", status_code=303)


@router.post("/consent/accept", response_class=HTMLResponse)
async def social_consent_accept(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/consent/accept — accept privacy terms."""
    ip_hash = sha256((request.client.host if request.client else "unknown").encode()).hexdigest()[:64]
    await record_consent(db, current_user.id, CURRENT_CONSENT_VERSION, ip_hash)
    return RedirectResponse(url="/social/profile", status_code=303)


# ---------------------------------------------------------------------------
# S0 — Privacy terms page
# ---------------------------------------------------------------------------


@router.get("/privacy", response_class=HTMLResponse)
async def social_privacy_page(request: Request):
    """GET /social/privacy — privacy policy (public, no auth required)."""
    locale = detect_locale(request)
    t = get_translations(locale)

    from app.auth import get_optional_user

    user = await get_optional_user(request)
    return templates.TemplateResponse(
        request,
        "social/privacy.html",
        {"t": t, "locale": locale, "user": user},
    )


# ---------------------------------------------------------------------------
# S1 — Subject registry API
# ---------------------------------------------------------------------------


@router.get("/subjects", response_class=HTMLResponse)
async def social_subjects_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GET /social/subjects — list your registered social subjects."""
    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)
    profile = await get_profile(db, current_user.id)

    if profile is None:
        return RedirectResponse(url="/social/profile", status_code=303)

    subjects = await list_owner_subjects(db, current_user.id)
    adapters = get_adapter_registry()

    return templates.TemplateResponse(
        request,
        "social/subjects.html",
        {
            "t": t,
            "locale": locale,
            "user": current_user,
            "profile": profile,
            "subjects": subjects,
            "adapters": adapters,
        },
    )


@router.get("/api/capabilities")
async def social_capabilities():
    """GET /social/api/capabilities — adapter registry info (public, no auth)."""
    adapters = get_adapter_registry()
    result = {}
    for ns, adapter in adapters.items():
        result[ns] = {
            "version": adapter.version,
            "subject_types": adapter.subject_types(),
        }
    return result


# ---------------------------------------------------------------------------
# S2 — Relationships page
# ---------------------------------------------------------------------------


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


# --- Invitation API ---


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
        if existing.cooldown_until and existing.cooldown_until > datetime.utcnow():
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


# --- Block API ---


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


# --- Grant API ---


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


# --- Notifications ---


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


# ---------------------------------------------------------------------------
# S3 — Publications & Feed
# ---------------------------------------------------------------------------


@router.get("/feed", response_class=HTMLResponse)
async def social_feed_page(
    request: Request,
    namespace: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GET /social/feed — cursor-based cross-domain feed."""
    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)
    profile = await get_profile(db, current_user.id)

    if profile is None:
        return RedirectResponse(url="/social/profile", status_code=303)

    publications = await list_feed(db, current_user.id, namespace=namespace, limit=30)

    # Enrich with owner alias
    pub_data = []
    for pub in publications:
        owner_profile = await get_profile(db, pub.owner_id)
        subject = await get_subject(db, pub.subject_id)
        pub_data.append(
            {
                "pub": pub,
                "owner_alias": owner_profile.alias if owner_profile else "unknown",
                "subject_type": subject.subject_type if subject else "unknown",
            }
        )

    # Also list owner's own publications for management
    own_pubs = await list_owner_publications(db, current_user.id)
    own_data = []
    for pub in own_pubs:
        subject = await get_subject(db, pub.subject_id)
        own_data.append(
            {
                "pub": pub,
                "subject_type": subject.subject_type if subject else "unknown",
            }
        )

    return templates.TemplateResponse(
        request,
        "social/feed.html",
        {
            "t": t,
            "locale": locale,
            "user": current_user,
            "profile": profile,
            "publications": pub_data,
            "own_publications": own_data,
            "current_namespace": namespace or "all",
        },
    )


@router.post("/publish", response_class=HTMLResponse)
async def social_publish(
    request: Request,
    subject_id: str = Form(...),
    visibility: str = Form("relationship_only"),
    snapshot_json: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/publish — publish a redacted snapshot of a domain subject."""
    import hashlib
    import json as _json

    subject_uuid = __import__("uuid").UUID(subject_id)
    subject = await get_subject(db, subject_uuid)
    if subject is None or subject.owner_id != current_user.id:
        raise HTTPException(404, "Subject not found")

    if visibility not in ("relationship_only", "unlisted", "public"):
        raise HTTPException(400, "Invalid visibility")

    try:
        snapshot = _json.loads(snapshot_json)
    except _json.JSONDecodeError:
        raise HTTPException(400, "Invalid snapshot JSON") from None

    snapshot_hash = hashlib.sha256(_json.dumps(snapshot, sort_keys=True).encode()).hexdigest()

    await create_publication(
        db,
        current_user.id,
        subject_uuid,
        visibility,
        snapshot,
        snapshot_hash,
        subject.subject_type.split(".")[0],
    )
    return RedirectResponse(url="/social/feed", status_code=303)


@router.post("/publish/{pub_id}/withdraw", response_class=HTMLResponse)
async def social_withdraw(
    pub_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/publish/{id}/withdraw — immediately remove publication."""
    pub_uuid = __import__("uuid").UUID(pub_id)
    pub = await withdraw_publication(db, pub_uuid, current_user.id)
    if pub is None:
        raise HTTPException(404, "Publication not found")
    return RedirectResponse(url="/social/feed", status_code=303)


# ---------------------------------------------------------------------------
# S4 — Verification, comments, encouragement
# ---------------------------------------------------------------------------


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


# --- Comments ---


@router.post("/comment", response_class=HTMLResponse)
async def social_comment_create(
    request: Request,
    target_type: str = Form(...),
    target_id: str = Form(...),
    body: str = Form(max_length=2000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/comment — create a comment."""
    if target_type not in ("publication", "verification_request"):
        raise HTTPException(400, "Invalid target type")
    await create_comment(
        db,
        current_user.id,
        target_type,
        __import__("uuid").UUID(target_id),
        body,
    )
    return RedirectResponse(url="/social/feed", status_code=303)


@router.post("/comment/{comment_id}/edit", response_class=HTMLResponse)
async def social_comment_edit(
    comment_id: str,
    body: str = Form(max_length=2000),
    redirect_url: str = Form("/social/feed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/comment/{id}/edit — edit own comment."""
    await edit_comment(db, __import__("uuid").UUID(comment_id), current_user.id, body)
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/comment/{comment_id}/delete", response_class=HTMLResponse)
async def social_comment_delete(
    comment_id: str,
    redirect_url: str = Form("/social/feed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/comment/{id}/delete — delete own comment."""
    await delete_comment(db, __import__("uuid").UUID(comment_id), current_user.id)
    return RedirectResponse(url=redirect_url, status_code=303)


# --- Encouragement ---


@router.post("/encourage", response_class=HTMLResponse)
async def social_encourage(
    request: Request,
    target_type: str = Form(...),
    target_id: str = Form(...),
    encouragement_type: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/encourage — send encouragement."""
    if encouragement_type not in ("thumbs_up", "support", "celebrate", "motivate"):
        raise HTTPException(400, "Invalid encouragement type")
    await create_encouragement(
        db,
        current_user.id,
        target_type,
        __import__("uuid").UUID(target_id),
        encouragement_type,
    )
    return RedirectResponse(url="/social/feed", status_code=303)


# ---------------------------------------------------------------------------
# S5 — Moderation (admin-only)
# ---------------------------------------------------------------------------


async def _check_moderator(user: User) -> None:
    """Only users in the owner allowlist can access moderation."""
    from app.api.locktimer_ui import _check_owner_allowlist

    _check_owner_allowlist(user)


@router.get("/moderation", response_class=HTMLResponse)
async def social_moderation_page(
    request: Request,
    state: str | None = None,
    target_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GET /social/moderation — moderator dashboard (admin-only)."""
    _check_moderator(current_user)
    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)

    reports = await list_reports(db, state=state, target_type=target_type, limit=100)

    # Enrich with reporter/target aliases (reporter NOT exposed to target in UI)
    enriched = []
    for report in reports:
        reporter_alias = None
        if report.reporter_id:
            reporter_profile = await get_profile(db, report.reporter_id)
            reporter_alias = reporter_profile.alias if reporter_profile else None

        # Get target context based on type
        target_desc = None
        if report.target_type == "publication":
            pub = await get_publication(db, report.target_id)
            if pub:
                subj = await get_subject(db, pub.subject_id)
                target_desc = f"Publication: {subj.subject_type if subj else 'unknown'}"
        elif report.target_type == "comment":
            target_desc = "Comment"
        else:
            target_desc = f"{report.target_type}: {report.target_id}"

        actions = await list_moderation_actions(db, report.id)
        enriched.append(
            {
                "report": report,
                "reporter_alias": reporter_alias or "anonymous",
                "target_desc": target_desc,
                "actions": actions,
            }
        )

    return templates.TemplateResponse(
        request,
        "social/moderation.html",
        {
            "t": t,
            "locale": locale,
            "user": current_user,
            "reports": enriched,
            "current_state": state or "all",
            "current_target_type": target_type or "all",
        },
    )


# --- Report filing (any authenticated user) ---


@router.post("/report", response_class=HTMLResponse)
async def social_report(
    request: Request,
    target_type: str = Form(...),
    target_id: str = Form(...),
    reason_code: str = Form(...),
    details: str | None = Form(None),
    redirect_url: str = Form("/social/feed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/report — file an abuse report. Reporter identity protected."""
    if target_type not in ("profile", "publication", "comment", "vote"):
        raise HTTPException(400, "Invalid target type")
    if reason_code not in (
        "harassment",
        "privacy",
        "non_consensual",
        "impersonation",
        "dangerous_content",
        "spam",
        "other",
    ):
        raise HTTPException(400, "Invalid reason code")

    await create_report(
        db,
        current_user.id,
        target_type,
        __import__("uuid").UUID(target_id),
        reason_code,
        details,
    )
    return RedirectResponse(url=redirect_url, status_code=303)


# --- Moderator actions (admin-only) ---


@router.post("/moderation/{report_id}/assign", response_class=HTMLResponse)
async def social_moderation_assign(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/moderation/{id}/assign — moderator takes a report."""
    _check_moderator(current_user)
    await assign_report(db, __import__("uuid").UUID(report_id), current_user.id)
    return RedirectResponse(url="/social/moderation", status_code=303)


@router.post("/moderation/{report_id}/action", response_class=HTMLResponse)
async def social_moderation_action(
    report_id: str,
    action_type: str = Form(...),
    reason: str = Form(...),
    action_target_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/moderation/{id}/action — execute a moderation action."""
    _check_moderator(current_user)

    if action_type not in (
        "hide_publication",
        "hide_comment",
        "invalidate_vote",
        "resolve_report",
        "dismiss_report",
        "request_evidence",
    ):
        raise HTTPException(400, "Invalid action type")

    report_uuid = __import__("uuid").UUID(report_id)
    report = await get_report(db, report_uuid)
    if report is None:
        raise HTTPException(404, "Report not found")

    # Execute domain action based on type
    action_metadata = {"target_id": action_target_id} if action_target_id else {}

    if action_type == "hide_publication" and action_target_id:
        ok = await hide_publication(db, __import__("uuid").UUID(action_target_id))
        if not ok:
            raise HTTPException(404, "Publication not found")
    elif action_type == "hide_comment" and action_target_id:
        ok = await hide_comment(db, __import__("uuid").UUID(action_target_id))
        if not ok:
            raise HTTPException(404, "Comment not found")
    elif action_type == "invalidate_vote" and action_target_id:
        ok = await invalidate_vote(db, __import__("uuid").UUID(action_target_id))
        if not ok:
            raise HTTPException(404, "Vote not found")
    elif action_type == "resolve_report":
        await resolve_report(db, report_uuid, current_user.id)
    elif action_type == "dismiss_report":
        await dismiss_report(db, report_uuid, current_user.id)

    # Record immutable action
    await create_moderation_action(
        db,
        report_uuid,
        current_user.id,
        action_type,
        reason,
        action_metadata,
    )
    return RedirectResponse(url="/social/moderation", status_code=303)
