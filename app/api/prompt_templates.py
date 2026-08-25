"""Prompt Templates API — thin HTTP wrappers over prompt_templates_service."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services.prompt_templates_service import (
    create_template,
    create_template_from_library,
    delete_template,
    execute_generation,
    get_library_context,
    get_template_detail_context,
    get_templates_page_context,
    get_user_prompt_library_items,
    list_templates,
    update_template,
)
from app.templates_setup import templates

router = APIRouter(tags=["prompt-templates"])
page_router = APIRouter(tags=["prompt-templates"])
json_router = APIRouter(prefix="/api/v2/prompt-templates", tags=["prompt-templates"])


# ── Pages ──


@page_router.get("/llm/prompts", response_class=HTMLResponse)
async def prompts_library_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = get_library_context(locale, t)
    return templates.TemplateResponse(
        request=request,
        name="prompt_library.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            **ctx,
        },
    )


@page_router.get("/llm/templates", response_class=HTMLResponse)
async def templates_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await get_templates_page_context(db, user)
    return templates.TemplateResponse(
        request=request,
        name="prompt_templates.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            **ctx,
        },
    )


@page_router.get("/prompts/library", response_class=HTMLResponse)
async def user_prompt_library_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await get_user_prompt_library_items(db)
    return templates.TemplateResponse(
        request=request,
        name="prompt_library_user.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "llm",
            **ctx,
        },
    )


@page_router.get("/llm/templates/{template_id}", response_class=HTMLResponse)
async def template_detail_page(
    template_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    try:
        ctx = await get_template_detail_context(db, user, template_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Template not found") from None
    return templates.TemplateResponse(
        request=request,
        name="prompt_template_detail.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            **ctx,
        },
    )


# ── CRUD (form posts) ──


@page_router.post("/llm/templates")
async def create_template_action(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    template_type: str = Form(default="text"),
    system_prompt: str = Form(...),
    params_schema: str = Form(default=""),
    source_key: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tpl = await create_template(
            db,
            user.id,
            name=name,
            description=description,
            template_type=template_type,
            system_prompt=system_prompt,
            params_schema=params_schema,
            source_key=source_key,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url=f"/llm/templates/{tpl.id}", status_code=status.HTTP_303_SEE_OTHER)


@page_router.post("/llm/templates/new-from-library")
async def create_from_library_action(
    request: Request,
    key: str = Form(...),
    name: str = Form(default=""),
    template_type: str = Form(default="text"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    t = get_translations(locale)
    try:
        tpl = await create_template_from_library(
            db, user.id, key, name=name, template_type=template_type, locale=locale, t=t,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url=f"/llm/templates/{tpl.id}", status_code=status.HTTP_303_SEE_OTHER)


@page_router.post("/llm/templates/{template_id}/update")
async def update_template_action(
    request: Request,
    template_id: uuid.UUID,
    name: str = Form(...),
    description: str = Form(default=""),
    template_type: str = Form(default="text"),
    system_prompt: str = Form(...),
    params_schema: str = Form(default=""),
    is_active: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        tpl = await update_template(
            db,
            user.id,
            template_id,
            name=name,
            description=description,
            template_type=template_type,
            system_prompt=system_prompt,
            params_schema=params_schema,
            is_active=is_active,
        )
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 400, str(e)) from None
    return RedirectResponse(url=f"/llm/templates/{tpl.id}", status_code=status.HTTP_303_SEE_OTHER)


@page_router.post("/llm/templates/{template_id}/delete")
async def delete_template_action(
    request: Request,
    template_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_template(db, user.id, template_id)
    except ValueError:
        raise HTTPException(404, detail="Template not found") from None
    return RedirectResponse(url="/llm/templates", status_code=status.HTTP_303_SEE_OTHER)


@page_router.post("/llm/templates/{template_id}/generate")
async def generate_template_action(
    request: Request,
    template_id: uuid.UUID,
    params_json: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {}
    if params_json.strip():
        try:
            parsed = json.loads(params_json)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"Params JSON invalid: {e}") from None
        if isinstance(parsed, dict):
            params = parsed

    locale = detect_locale(request, user.locale)
    try:
        outcome = await execute_generation(db, user.id, template_id, locale, params)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(404, msg) from None
        if "LLM provider" in msg:
            raise HTTPException(409, msg) from None
        raise HTTPException(400, msg) from None

    if outcome["type"] == "task":
        return RedirectResponse(
            url=f"/llm/templates/{template_id}?result=task&task_id={outcome['activity_log_id']}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=f"/llm/templates/{template_id}?result=text&text={outcome['content'][:4000]}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ── JSON API ──


@json_router.get("")
async def json_list_templates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_templates(db, user.id)


class GenerateRequest(BaseModel):
    params: dict | None = None


@json_router.post("/{template_id}/generate")
async def json_generate_template(
    template_id: uuid.UUID,
    body: GenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        outcome = await execute_generation(
            db, user.id, template_id, user.locale or "en", body.params,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(404, msg) from None
        if "LLM provider" in msg:
            raise HTTPException(409, msg) from None
        raise HTTPException(400, msg) from None
    return JSONResponse(outcome)
