"""Social publications & feed (S3)."""

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
    create_publication,
    get_profile,
    get_subject,
    list_feed,
    list_owner_publications,
    withdraw_publication,
)
from app.templates_setup import templates

router = APIRouter(tags=["social"])


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
