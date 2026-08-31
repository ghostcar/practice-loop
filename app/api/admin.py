"""Admin Panel — thin HTTP wrappers over app.services.admin_service."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.llm_catalog import LLMGlobalModel, LLMGlobalProvider
from app.models.user import User
from app.seed import seed_llm_presets
from app.seed_body_parts import seed_body_parts
from app.seed_inventory_categories import seed_inventory_categories
from app.seed_locations import seed_locations
from app.services.admin_service import (
    execute_ai_generator,
    get_catalog_editor_context,
    get_prompts_hub_context,
    get_schema_builder_context,
    get_user_list_context,
    reset_prompt_item,
    reset_user_password,
    set_user_disabled,
    set_user_role,
    update_prompt_item,
)
from app.templates_setup import templates

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request, user: User = Depends(require_admin)):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "admin",
        },
    )


@router.get("/llm-pool", response_class=HTMLResponse)
async def admin_llm_pool(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    providers = (await db.execute(select(LLMGlobalProvider).order_by(LLMGlobalProvider.name))).scalars().all()
    return templates.TemplateResponse(
        request,
        "admin_llm_pool.html",
        {
            "request": request,
            "t": get_translations(detect_locale(request, user.locale)),
            "user": user,
            "locale": detect_locale(request, user.locale),
            "theme": detect_theme(user.theme),
            "active_nav": "admin",
            "providers": providers,
        },
    )


@router.post("/llm-pool/providers")
async def admin_create_llm_provider(
    name: str = Form(...),
    api_base_url: str = Form(...),
    supports_text: bool = Form(default=True),
    supports_vision: bool = Form(default=False),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    db.add(
        LLMGlobalProvider(
            name=name.strip(),
            api_base_url=api_base_url.strip(),
            supports_text=supports_text,
            supports_vision=supports_vision,
        )
    )
    await db.flush()
    return RedirectResponse(url="/admin/llm-pool", status_code=303)


@router.post("/llm-pool/providers/{provider_id}/models")
async def admin_add_llm_model(
    provider_id: uuid.UUID,
    model_name: str = Form(...),
    supports_text: bool = Form(default=True),
    supports_vision: bool = Form(default=False),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    provider = await db.scalar(select(LLMGlobalProvider).where(LLMGlobalProvider.id == provider_id))
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    db.add(
        LLMGlobalModel(
            provider_id=provider.id,
            model_name=model_name.strip(),
            supports_text=supports_text,
            supports_vision=supports_vision,
        )
    )
    await db.flush()
    return RedirectResponse(url="/admin/llm-pool", status_code=303)


@router.post("/seed-entities")
async def seed_entities_endpoint(user: User = Depends(require_admin)):
    raise HTTPException(410, "Legacy entity seed is retired")


@router.post("/seed-llm-presets")
async def seed_llm_presets_endpoint(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await seed_llm_presets(db, user_id=user.id)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/seed-references")
async def seed_references_endpoint(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await seed_body_parts(db)
    await seed_locations(db)
    await seed_inventory_categories(db)
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/users", response_class=HTMLResponse)
async def admin_users_page(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    ctx = await get_user_list_context(db)
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "t": get_translations(detect_locale(request, user.locale)),
            "theme": detect_theme(user.theme),
            "user": user,
            "locale": detect_locale(request, user.locale),
            "nav_key": "admin",
            **ctx,
        },
    )


@router.post("/users/{user_id}/role")
async def admin_set_user_role(
    user_id: uuid.UUID,
    role: str = Form(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await set_user_role(db, user_id, role, admin.id)
    except ValueError as e:
        raise HTTPException(409 if "demote" in str(e) else 400, str(e)) from None
    return RedirectResponse(url="/admin/users?status=role", status_code=303)


@router.post("/users/{user_id}/disabled")
async def admin_set_user_disabled(
    user_id: uuid.UUID,
    disabled: bool = Form(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await set_user_disabled(db, user_id, disabled, admin.id)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    return RedirectResponse(url="/admin/users?status=disabled", status_code=303)


@router.post("/users/{user_id}/password")
async def admin_reset_user_password(
    user_id: uuid.UUID,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await reset_user_password(db, user_id, new_password, confirm_password, admin.id)
    except ValueError as e:
        raise HTTPException(409 if "own" in str(e).lower() else 400, str(e)) from None
    return RedirectResponse(url="/admin/users?status=password", status_code=303)


@router.get("/schema-builder", response_class=HTMLResponse)
async def admin_schema_builder(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    ctx = await get_schema_builder_context(db)
    locale = detect_locale(request, admin.locale)
    return templates.TemplateResponse(
        request=request,
        name="admin_schema_builder.html",
        context={
            "request": request,
            "t": get_translations(locale),
            "user": admin,
            "locale": locale,
            "theme": detect_theme(admin.theme),
            "active_nav": "admin",
            **ctx,
        },
    )


@router.get("/catalog-editor", response_class=HTMLResponse)
async def admin_catalog_editor(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    ctx = await get_catalog_editor_context(db)
    locale = detect_locale(request, admin.locale)
    return templates.TemplateResponse(
        request=request,
        name="admin_catalog_editor.html",
        context={
            "request": request,
            "t": get_translations(locale),
            "user": admin,
            "locale": locale,
            "theme": detect_theme(admin.theme),
            "active_nav": "admin",
            **ctx,
        },
    )


@router.get("/ai-generator", response_class=HTMLResponse)
async def admin_ai_generator_page(request: Request, admin: User = Depends(require_admin)):
    locale = detect_locale(request, admin.locale)
    return templates.TemplateResponse(
        request=request,
        name="admin_ai_generator.html",
        context={
            "request": request,
            "t": get_translations(locale),
            "user": admin,
            "locale": locale,
            "theme": detect_theme(admin.theme),
            "active_nav": "admin",
            "generated_items": [],
        },
    )


@router.post("/ai-generator/generate", response_class=HTMLResponse)
async def admin_ai_generator_execute(
    request: Request,
    mode: str = Form(default="expanded"),
    explicit_level: int = Form(default=4),
    remove_filters: bool = Form(default=False),
    custom_directives: str = Form(default=""),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    generated_items = await execute_ai_generator(
        db,
        admin.id,
        mode=mode,
        explicit_level=explicit_level,
        remove_filters=remove_filters,
        custom_directives=custom_directives,
    )
    locale = detect_locale(request, admin.locale)
    return templates.TemplateResponse(
        request=request,
        name="admin_ai_generator.html",
        context={
            "request": request,
            "t": get_translations(locale),
            "user": admin,
            "locale": locale,
            "theme": detect_theme(admin.theme),
            "active_nav": "admin",
            "generated_items": generated_items,
        },
    )


@router.get("/prompts", response_class=HTMLResponse)
async def admin_prompts_hub(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    ctx = await get_prompts_hub_context(db)
    locale = detect_locale(request, user.locale)
    return templates.TemplateResponse(
        request=request,
        name="admin_prompts.html",
        context={
            "request": request,
            "t": get_translations(locale),
            "user": user,
            "locale": locale,
            "theme": detect_theme(user.theme),
            "active_nav": "admin",
            **ctx,
        },
    )


@router.post("/prompts/{prompt_id}/update")
async def update_prompt_item_route(
    prompt_id: uuid.UUID,
    template_content: str = Form(...),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await update_prompt_item(db, prompt_id, template_content)
    except ValueError:
        raise HTTPException(404, "Prompt item not found") from None
    return RedirectResponse(url="/admin/prompts", status_code=303)


@router.post("/prompts/{prompt_id}/reset")
async def reset_prompt_item_route(
    prompt_id: uuid.UUID,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await reset_prompt_item(db, prompt_id)
    except ValueError:
        raise HTTPException(404, "Prompt item not found") from None
    return RedirectResponse(url="/admin/prompts", status_code=303)
