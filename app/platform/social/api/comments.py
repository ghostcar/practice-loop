"""Social comments + encouragements (S4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.platform.social.repositories import (
    create_comment,
    create_encouragement,
    delete_comment,
    edit_comment,
)

router = APIRouter(tags=["social"])


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
