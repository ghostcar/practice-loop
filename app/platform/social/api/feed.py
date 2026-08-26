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
from app.platform.social import get_adapter_registry
from app.platform.social.repositories import (
    create_publication,
    get_profile,
    get_subject,
    list_feed,
    list_owner_publications,
    list_owner_subjects,
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
    owner_subjects = await list_owner_subjects(db, current_user.id)

    # Enrich with owner alias + block-filtered comments
    from app.platform.social.repositories import list_comments

    pub_data = []
    for pub in publications:
        owner_profile = await get_profile(db, pub.owner_id)
        subject = await get_subject(db, pub.subject_id)
        comments = await list_comments(db, "publication", pub.id, viewer_id=current_user.id)
        comment_data = []
        for c in comments:
            author_profile = await get_profile(db, c.author_id)
            comment_data.append(
                {
                    "comment": c,
                    "author_alias": author_profile.alias if author_profile else "unknown",
                }
            )
        pub_data.append(
            {
                "pub": pub,
                "owner_alias": owner_profile.alias if owner_profile else "unknown",
                "subject_type": subject.subject_type if subject else "unknown",
                "comments": comment_data,
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
            "owner_subjects": owner_subjects,
            "current_namespace": namespace or "all",
        },
    )


@router.post("/publish", response_class=HTMLResponse)
async def social_publish(
    request: Request,
    subject_id: str = Form(...),
    visibility: str = Form("relationship_only"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST /social/publish — publish a redacted snapshot of a domain subject.

    The snapshot is ALWAYS rebuilt through the subject's registered adapter
    (the redaction layer) — clients never craft snapshots themselves.
    """
    import hashlib
    import json as _json
    import uuid as _uuid

    try:
        subject_uuid = _uuid.UUID(subject_id)
    except (ValueError, AttributeError):
        raise HTTPException(400, "Invalid subject id") from None

    subject = await get_subject(db, subject_uuid)
    if subject is None or subject.owner_id != current_user.id:
        raise HTTPException(404, "Subject not found")

    if visibility not in ("relationship_only", "unlisted", "public"):
        raise HTTPException(400, "Invalid visibility")

    namespace = subject.subject_type.split(".", 1)[0]
    adapter = get_adapter_registry().get(namespace)
    if adapter is None:
        raise HTTPException(400, f"No adapter registered for namespace '{namespace}'")

    snapshot = await adapter.build_redacted_projection(db, str(subject.domain_object_id))
    if not snapshot:
        raise HTTPException(400, "Adapter returned an empty projection — nothing to publish")

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
