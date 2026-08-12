"""Social moderation — reports, actions (S5)."""

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
    assign_report,
    create_moderation_action,
    create_report,
    dismiss_report,
    get_profile,
    get_publication,
    get_report,
    get_subject,
    hide_comment,
    hide_publication,
    invalidate_vote,
    list_moderation_actions,
    list_reports,
    resolve_report,
)
from app.templates_setup import templates

router = APIRouter(tags=["social"])


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
