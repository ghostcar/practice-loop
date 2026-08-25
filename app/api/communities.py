"""Community Registry — thin HTTP wrappers over app.services.communities_service."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services.communities_service import (
    create_community_from_form,
    do_add_moderator,
    do_approve_member,
    do_ban_member,
    do_create_post,
    do_delete_community,
    do_join_community,
    do_leave_community,
    do_remove_moderator,
    do_rotate_invite,
    do_transfer_ownership,
    do_unban_member,
    get_community_detail_context,
    get_community_feed_context,
    get_community_list_context,
)
from app.templates_setup import templates

router = APIRouter(tags=["communities"])


@router.get("/communities", response_class=HTMLResponse)
async def community_list_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await get_community_list_context(db, user)
    return templates.TemplateResponse(
        request=request,
        name="community_list.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "communities",
            "creation_limit": getattr(settings, "community_creation_limit", 0),
            **ctx,
        },
    )


@router.post("/communities/create")
async def create_community_endpoint(
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(""),
    visibility: str = Form("public"),
    require_approval: str = Form("off"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    limit = getattr(settings, "community_creation_limit", 0)
    community, error_url = await create_community_from_form(
        db,
        user.id,
        name=name,
        slug=slug,
        description=description,
        visibility=visibility,
        require_approval=require_approval == "on",
        creation_limit=limit,
    )
    if error_url:
        return RedirectResponse(url=error_url, status_code=303)
    return RedirectResponse(url=f"/communities/{community.id}", status_code=303)


@router.get("/communities/{community_id}", response_class=HTMLResponse)
async def community_detail_page(
    community_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        c_uuid = uuid.UUID(community_id)
    except ValueError:
        raise HTTPException(400, "Invalid community ID") from None
    try:
        ctx = await get_community_detail_context(db, c_uuid, user)
    except ValueError:
        raise HTTPException(404, "Community not found") from None
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="community_detail.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "communities",
            **ctx,
        },
    )


@router.get("/communities/{community_id}/feed", response_class=HTMLResponse)
async def community_feed_page(
    community_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        c_uuid = uuid.UUID(community_id)
    except ValueError:
        raise HTTPException(400, "Invalid community ID") from None
    try:
        ctx = await get_community_feed_context(db, c_uuid, user)
    except ValueError:
        raise HTTPException(404, "Community not found") from None
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="community_feed.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "communities",
            **ctx,
        },
    )


@router.post("/communities/{community_id}/feed/post")
async def create_community_post_endpoint(
    community_id: str,
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        await do_create_post(db, c_uuid, user, title=title, content=content)
    except ValueError as e:
        raise HTTPException(403, str(e)) from None
    return RedirectResponse(url=f"/communities/{c_uuid}/feed", status_code=303)


@router.post("/communities/{community_id}/members/ban")
async def ban_member_endpoint(
    community_id: str,
    user_id: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        await do_ban_member(db, c_uuid, uuid.UUID(user_id), user.id)
    except (ValueError, PermissionError) as e:
        code = 403 if isinstance(e, PermissionError) else 404
        raise HTTPException(code, str(e)) from None
    return RedirectResponse(url=f"/communities/{c_uuid}?mod=ban", status_code=303)


@router.post("/communities/{community_id}/members/unban")
async def unban_member_endpoint(
    community_id: str,
    user_id: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        await do_unban_member(db, c_uuid, uuid.UUID(user_id), user.id)
    except (ValueError, PermissionError) as e:
        code = 403 if isinstance(e, PermissionError) else 404
        raise HTTPException(code, str(e)) from None
    return RedirectResponse(url=f"/communities/{c_uuid}?mod=unban", status_code=303)


@router.post("/communities/{community_id}/join")
async def join_community_endpoint(
    community_id: str,
    request: Request,
    invite_code: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        redirect_url = await do_join_community(db, c_uuid, user.id, invite_code)
    except ValueError:
        raise HTTPException(404, "Community not found") from None
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/communities/{community_id}/leave")
async def leave_community_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    removed = await do_leave_community(db, c_uuid, user.id)
    if not removed:
        raise HTTPException(400, "Владелец не может покинуть сообщество (или вы не участник)")
    return RedirectResponse(url="/communities", status_code=303)


@router.post("/communities/{community_id}/approve")
async def approve_member_endpoint(
    community_id: str,
    member_id: str = Form(...),
    decision: str = Form("approve"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        await do_approve_member(db, c_uuid, uuid.UUID(member_id), user.id, decision == "approve")
    except ValueError as e:
        code = 403 if "владелец" in str(e).lower() else 404
        raise HTTPException(code, str(e)) from None
    return RedirectResponse(url=f"/communities/{c_uuid}", status_code=303)


@router.post("/communities/{community_id}/invite")
async def generate_invite_code_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        code = await do_rotate_invite(db, c_uuid, user.id)
    except ValueError as e:
        raise HTTPException(403, str(e)) from None
    return RedirectResponse(url=f"/communities/{c_uuid}?invite={code}", status_code=303)


@router.post("/communities/{community_id}/delete")
async def delete_community_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        await do_delete_community(db, c_uuid, user.id)
    except ValueError as e:
        raise HTTPException(403, str(e)) from None
    return RedirectResponse(url="/communities", status_code=303)


@router.post("/communities/{community_id}/transfer")
async def transfer_ownership_endpoint(
    community_id: str,
    new_owner_id: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        status = await do_transfer_ownership(db, c_uuid, uuid.UUID(new_owner_id), user.id)
    except ValueError as e:
        raise HTTPException(403, str(e)) from None
    if status == "not_member":
        raise HTTPException(400, "Новый владелец должен быть активным участником сообщества")
    if status == "already_owner":
        raise HTTPException(400, "Этот участник уже является владельцем")
    return RedirectResponse(url=f"/communities/{c_uuid}?transfer=ok", status_code=303)


@router.post("/communities/{community_id}/moderators/add")
async def add_moderator_endpoint(
    community_id: str,
    user_id_: str = Form(..., alias="user_id"),
    role_type: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        status = await do_add_moderator(db, c_uuid, uuid.UUID(user_id_), role_type, user.id)
    except ValueError as e:
        raise HTTPException(403, str(e)) from None
    if status == "invalid_role":
        raise HTTPException(400, "Неизвестная роль модератора")
    if status == "not_member":
        raise HTTPException(400, "Участник должен быть активным членом сообщества")
    if status == "already_assigned":
        raise HTTPException(400, "Роль уже назначена этому участнику")
    return RedirectResponse(url=f"/communities/{c_uuid}?moderator=added", status_code=303)


@router.post("/communities/{community_id}/moderators/remove")
async def remove_moderator_endpoint(
    community_id: str,
    user_id_: str = Form(..., alias="user_id"),
    role_type: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    try:
        removed = await do_remove_moderator(db, c_uuid, uuid.UUID(user_id_), role_type, user.id)
    except ValueError as e:
        raise HTTPException(403, str(e)) from None
    if not removed:
        raise HTTPException(400, "Роль не была назначена")
    return RedirectResponse(url=f"/communities/{c_uuid}?moderator=removed", status_code=303)
