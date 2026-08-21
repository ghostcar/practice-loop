"""Prompt templates API (ADR-070, Step 6).

Pages:
- GET  /llm/prompts           — библиотека типовых промптов (+ «создать шаблон из этого»)
- GET  /llm/templates         — приватные шаблоны пользователя (list + create form)
- GET  /llm/templates/{id}    — просмотр/редактирование одного шаблона

Actions:
- POST /llm/templates                    — создать шаблон
- POST /llm/templates/{id}/update        — обновить
- POST /llm/templates/{id}/delete        — удалить
- POST /llm/templates/{id}/generate      — запустить генерацию (text | task)
- POST /llm/templates/new-from-library   — создать приватный шаблон из библиотеки

JSON API (для будущего mobile/ботов):
- GET  /api/v2/prompt-templates
- POST /api/v2/prompt-templates/{id}/generate (body: {"params": {...}})
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.pipeline.generate import get_active_llm_config
from app.llm.pipeline.templates import (
    extract_template_vars,
    generate_from_template,
)
from app.llm.prompt_library import list_prompts, prompt_categories, render_system_prompt
from app.models.prompt_template import PromptTemplate
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(tags=["prompt-templates"])

# Page router (no prefix — absolute paths for forms)
page_router = APIRouter(tags=["prompt-templates"])
# JSON router
json_router = APIRouter(prefix="/api/v2/prompt-templates", tags=["prompt-templates"])

MAX_PROMPT_LEN = 20_000
MAX_NAME_LEN = 200


def _serialize(t: PromptTemplate) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "description": t.description,
        "template_type": t.template_type,
        "system_prompt": t.system_prompt,
        "params_schema": t.params_schema,
        "is_active": t.is_active,
        "source_key": t.source_key,
        "usage_count": t.usage_count,
        "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
        "vars": extract_template_vars(t.system_prompt),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────


@page_router.get("/llm/prompts", response_class=HTMLResponse)
async def prompts_library_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Библиотека типовых промптов."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    prompts = []
    for p in list_prompts():
        prompts.append(
            {
                "key": p.key,
                "category": p.category,
                "title": t.get(p.title_key, p.key),
                "description": t.get(p.description_key, ""),
                "preview": render_system_prompt(p, locale=locale)[:400],
                "vars": list(p.format_vars),
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="prompt_library.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "prompts": prompts,
            "categories": prompt_categories(),
        },
    )


@page_router.get("/llm/templates", response_class=HTMLResponse)
async def templates_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список приватных промпт-шаблонов пользователя."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.user_id == user.id).order_by(PromptTemplate.created_at.desc())
    )
    templates_list = [_serialize(pt) for pt in result.scalars().all()]
    llm_config = await get_active_llm_config(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="prompt_templates.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "templates": templates_list,
            "has_llm_config": llm_config is not None,
            "library_prompts": [
                {"key": p.key, "title": t.get(p.title_key, p.key), "category": p.category} for p in list_prompts()
            ],
        },
    )


@page_router.get("/prompts/library", response_class=HTMLResponse)
async def user_prompt_library_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Categorized Prompt Library Hub (System & User Prompts)."""
    from app.models.prompt_library import PromptLibraryItem

    items = (await db.execute(select(PromptLibraryItem).order_by(PromptLibraryItem.key))).scalars().all()

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    system_prompts = [i for i in items if i.library_type == "system"]
    user_prompts = [i for i in items if i.library_type == "user"]

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
            "system_prompts": system_prompts,
            "user_prompts": user_prompts,
        },
    )


@page_router.get("/llm/templates/{template_id}", response_class=HTMLResponse)
async def template_detail_page(
    template_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Просмотр/редактирование одного шаблона."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id, PromptTemplate.user_id == user.id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    data = _serialize(template)
    schema_json = json.dumps(template.params_schema, ensure_ascii=False, indent=2) if template.params_schema else ""
    data["params_schema_json"] = schema_json
    data["vars"] = extract_template_vars(template.system_prompt)
    llm_config = await get_active_llm_config(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="prompt_template_detail.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "template": data,
            "has_llm_config": llm_config is not None,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# CRUD (form posts)
# ─────────────────────────────────────────────────────────────────────────────


def _validate_schema_json(raw: str) -> dict | list | None:
    """Parse and sanitize the params_schema JSON (ADR-041 format)."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"params_schema is not valid JSON: {e}") from e
    if not isinstance(parsed, dict | list):
        raise HTTPException(400, "params_schema must be a JSON object or array")
    # Validate the shape via the typed DSL (raises ValueError on bad definitions).
    from app.params import normalize_schema

    try:
        normalize_schema(parsed)
    except ValueError as e:
        raise HTTPException(400, f"Invalid params_schema: {e}") from e
    return parsed


@page_router.post("/llm/templates")
async def create_template(
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
    """Create a private prompt template."""
    name = name.strip()[:MAX_NAME_LEN]
    if not name:
        raise HTTPException(400, "Template name is required")
    if len(system_prompt) > MAX_PROMPT_LEN:
        raise HTTPException(400, "System prompt is too long")
    ttype = template_type.strip().lower()
    if ttype not in ("text", "task"):
        ttype = "text"

    schema = _validate_schema_json(params_schema)
    template = PromptTemplate(
        user_id=user.id,
        name=name,
        description=(description or "").strip()[:2000] or None,
        template_type=ttype,
        system_prompt=system_prompt,
        params_schema=schema,
        source_key=(source_key or "").strip()[:50] or None,
    )
    db.add(template)
    await db.flush()
    return RedirectResponse(url=f"/llm/templates/{template.id}", status_code=status.HTTP_303_SEE_OTHER)


@page_router.post("/llm/templates/new-from-library")
async def create_template_from_library(
    request: Request,
    key: str = Form(...),
    name: str = Form(default=""),
    template_type: str = Form(default="text"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a private template from a library prompt."""
    from app.llm.prompt_library import get_prompt

    prompt_def = get_prompt(key)
    if prompt_def is None:
        raise HTTPException(400, f"Unknown library prompt: {key}")

    locale = detect_locale(request, user.locale)
    t = get_translations(locale)
    system_prompt = render_system_prompt(prompt_def, locale=locale)
    default_name = name.strip() or t.get(prompt_def.title_key, key)

    template = PromptTemplate(
        user_id=user.id,
        name=default_name[:MAX_NAME_LEN],
        description=t.get(prompt_def.description_key, ""),
        template_type=template_type,
        system_prompt=system_prompt,
        source_key=prompt_def.key,
    )
    db.add(template)
    await db.flush()
    return RedirectResponse(url=f"/llm/templates/{template.id}", status_code=status.HTTP_303_SEE_OTHER)


@page_router.post("/llm/templates/{template_id}/update")
async def update_template(
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
    """Update a private prompt template."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id, PromptTemplate.user_id == user.id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    template.name = (name or template.name).strip()[:MAX_NAME_LEN]
    template.description = (description or "").strip()[:2000] or None
    ttype = template_type.strip().lower()
    if ttype in ("text", "task"):
        template.template_type = ttype
    if system_prompt and len(system_prompt) <= MAX_PROMPT_LEN:
        template.system_prompt = system_prompt
    template.params_schema = _validate_schema_json(params_schema)
    template.is_active = is_active.strip().lower() in {"1", "on", "true", "yes"}
    db.add(template)
    await db.flush()
    return RedirectResponse(url=f"/llm/templates/{template.id}", status_code=status.HTTP_303_SEE_OTHER)


@page_router.post("/llm/templates/{template_id}/delete")
async def delete_template(
    request: Request,
    template_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a private prompt template."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id, PromptTemplate.user_id == user.id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(template)
    await db.flush()
    return RedirectResponse(url="/llm/templates", status_code=status.HTTP_303_SEE_OTHER)


@page_router.post("/llm/templates/{template_id}/generate")
async def generate_template_action(
    request: Request,
    template_id: uuid.UUID,
    params_json: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run generation from a template (form post) and show the result page."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id, PromptTemplate.user_id == user.id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        raise HTTPException(status_code=409, detail="No active LLM provider configured")

    params: dict = {}
    if params_json.strip():
        try:
            parsed = json.loads(params_json)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"Params JSON invalid: {e}") from e
        if isinstance(parsed, dict):
            params = parsed

    locale = detect_locale(request, user.locale)

    try:
        outcome = await generate_from_template(
            db=db,
            user_id=user.id,
            llm_config=llm_config,
            template=template,
            params=params,
            locale=locale,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    # Track usage + bump counter (text path needs the db update here).
    usage = outcome.get("usage", {})
    llm_config.total_tokens += usage.get("total_tokens", 0)
    llm_config.total_cost += usage.get("cost", 0.0)
    template.usage_count += 1
    from datetime import UTC, datetime

    template.last_used_at = datetime.now(UTC)
    db.add(llm_config)
    db.add(template)
    await db.flush()

    if outcome["type"] == "task":
        return RedirectResponse(
            url=f"/llm/templates/{template.id}?result=task&task_id={outcome['activity_log_id']}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/llm/templates/{template.id}?result=text&text={outcome['content'][:4000]}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ─────────────────────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("")
async def json_list_templates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.user_id == user.id).order_by(PromptTemplate.created_at.desc())
    )
    return [_serialize(pt) for pt in result.scalars().all()]


class GenerateRequest(BaseModel):
    params: dict | None = None


@json_router.post("/{template_id}/generate")
async def json_generate_template(
    template_id: uuid.UUID,
    body: GenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a template via JSON API — returns structured result (text or task)."""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id, PromptTemplate.user_id == user.id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        raise HTTPException(status_code=409, detail="No active LLM provider configured")

    try:
        outcome = await generate_from_template(
            db=db,
            user_id=user.id,
            llm_config=llm_config,
            template=template,
            params=body.params or {},
            locale=user.locale or "en",
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    usage = outcome.get("usage", {})
    llm_config.total_tokens += usage.get("total_tokens", 0)
    llm_config.total_cost += usage.get("cost", 0.0)
    template.usage_count += 1
    from datetime import UTC, datetime

    template.last_used_at = datetime.now(UTC)
    db.add(llm_config)
    db.add(template)
    await db.flush()

    return JSONResponse(outcome)
