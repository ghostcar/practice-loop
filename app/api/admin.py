import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password, require_admin
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.api_token import ApiToken
from app.models.user import User
from app.seed import seed_llm_presets
from app.seed_body_parts import seed_body_parts
from app.seed_inventory_categories import seed_inventory_categories
from app.seed_locations import seed_locations
from app.templates_setup import templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
USER_ROLES = ("user", "moderator", "admin")


@router.get("/", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    user: User = Depends(require_admin),
):
    """Admin dashboard — requires admin role."""
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


@router.post("/seed-entities")
async def seed_entities_endpoint(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reject the retired legacy catalog until its reviewed manifest is ready."""
    raise HTTPException(status_code=410, detail="Legacy entity seed is retired; use the reviewed catalog manifest")


@router.post("/seed-llm-presets")
async def seed_llm_presets_endpoint(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Seed LLM presets — requires admin role."""
    await seed_llm_presets(db, user_id=user.id)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/seed-references")
async def seed_references_endpoint(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Seed reference data: body parts, locations, inventory categories."""
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
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "t": get_translations(detect_locale(request, user.locale)),
            "theme": detect_theme(user.theme),
            "user": user,
            "users": users,
            "roles": USER_ROLES,
            "nav_key": "admin",
        },
    )


async def _managed_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "User not found")
    return target


@router.post("/users/{user_id}/role")
async def admin_set_user_role(
    user_id: uuid.UUID,
    role: str = Form(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if role not in USER_ROLES:
        raise HTTPException(400, "Invalid role")
    target = await _managed_user(db, user_id)
    if target.id == admin.id and role != "admin":
        raise HTTPException(409, "An administrator cannot demote their own account")
    target.role = role
    db.add(target)
    await db.flush()
    return RedirectResponse(url="/admin/users?status=role", status_code=303)


@router.post("/users/{user_id}/disabled")
async def admin_set_user_disabled(
    user_id: uuid.UUID,
    disabled: bool = Form(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await _managed_user(db, user_id)
    if target.id == admin.id and disabled:
        raise HTTPException(409, "An administrator cannot disable their own account")
    target.disabled_at = datetime.now(UTC) if disabled else None
    db.add(target)
    if disabled:
        await db.execute(delete(ApiToken).where(ApiToken.user_id == target.id))
    await db.flush()
    return RedirectResponse(url="/admin/users?status=disabled", status_code=303)


@router.post("/users/{user_id}/password")
async def admin_reset_user_password(
    user_id: uuid.UUID,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await _managed_user(db, user_id)
    if target.id == admin.id:
        raise HTTPException(409, "Use account settings to change your own password")
    if not 6 <= len(new_password) <= 128:
        raise HTTPException(400, "Password must contain 6-128 characters")
    if new_password != confirm_password:
        raise HTTPException(400, "Passwords do not match")
    target.password_hash = hash_password(new_password)
    db.add(target)
    await db.execute(delete(ApiToken).where(ApiToken.user_id == target.id))
    await db.flush()
    return RedirectResponse(url="/admin/users?status=password", status_code=303)


@router.get("/schema-builder", response_class=HTMLResponse)
async def admin_schema_builder(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Interactive Parameter Schema Builder workbench (Step 25)."""
    from app.models.entity import Entity

    locale = detect_locale(request, admin.locale)
    theme = detect_theme(admin.theme)
    t = get_translations(locale)

    entities = (await db.execute(select(Entity))).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="admin_schema_builder.html",
        context={
            "request": request,
            "t": t,
            "user": admin,
            "locale": locale,
            "theme": theme,
            "active_nav": "admin",
            "entities": entities,
        },
    )


@router.get("/catalog-editor", response_class=HTMLResponse)
async def admin_catalog_editor(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Interactive Catalog & Seed Editor workbench."""
    from app.models.entity import Entity

    locale = detect_locale(request, admin.locale)
    theme = detect_theme(admin.theme)
    t = get_translations(locale)

    entities = (await db.execute(select(Entity).order_by(Entity.created_at.desc()))).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="admin_catalog_editor.html",
        context={
            "request": request,
            "t": t,
            "user": admin,
            "locale": locale,
            "theme": theme,
            "active_nav": "admin",
            "items": entities,
        },
    )


@router.get("/ai-generator", response_class=HTMLResponse)
async def admin_ai_generator_page(
    request: Request,
    admin: User = Depends(require_admin),
):
    """AI Portal Content Generator & Conscious Prompt Workbench (Step 40)."""
    locale = detect_locale(request, admin.locale)
    theme = detect_theme(admin.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="admin_ai_generator.html",
        context={
            "request": request,
            "t": t,
            "user": admin,
            "locale": locale,
            "theme": theme,
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
    """Executes AI Content Generation with conscious filter/prompt overrides."""
    from app.llm.pipeline import get_active_llm_config
    from app.llm.pipeline.content_generator import (
        build_catalog_generation_prompt,
        generate_catalog_proposals,
    )

    locale = detect_locale(request, admin.locale)
    theme = detect_theme(admin.theme)
    t = get_translations(locale)

    llm_config = await get_active_llm_config(db, admin.id)
    generated_items = []

    if llm_config:
        sys_prompt, usr_prompt = build_catalog_generation_prompt(
            mode=mode,
            explicit_level=explicit_level,
            custom_directives=custom_directives,
            remove_filters=remove_filters,
        )
        try:
            generated_items = await generate_catalog_proposals(
                db=db,
                user_id=admin.id,
                llm_config=llm_config,
                system_prompt=sys_prompt,
                user_prompt=usr_prompt,
            )
        except Exception as e:
            logger.error(f"AI Catalog Generation failed: {e}")

    return templates.TemplateResponse(
        request=request,
        name="admin_ai_generator.html",
        context={
            "request": request,
            "t": t,
            "user": admin,
            "locale": locale,
            "theme": theme,
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
    """Prompt Library Management Hub for System and User prompts."""
    from app.models.prompt_library import PromptLibraryItem
    from app.prompt_library import seed_prompt_library

    # Auto seed if empty
    await seed_prompt_library(db)

    items = (await db.execute(select(PromptLibraryItem).order_by(PromptLibraryItem.key))).scalars().all()

    system_prompts = [i for i in items if i.library_type == "system"]
    user_prompts = [i for i in items if i.library_type == "user"]

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="admin_prompts.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "admin",
            "system_prompts": system_prompts,
            "user_prompts": user_prompts,
        },
    )


@router.post("/prompts/{prompt_id}/update")
async def update_prompt_item(
    prompt_id: uuid.UUID,
    template_content: str = Form(...),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Updates a prompt template content in the library."""
    from app.models.prompt_library import PromptLibraryItem

    item = (await db.execute(select(PromptLibraryItem).where(PromptLibraryItem.id == prompt_id))).scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Prompt item not found")

    item.template_content = template_content
    item.is_customized = True
    item.updated_at = datetime.now(UTC)

    await db.commit()
    return RedirectResponse(url="/admin/prompts", status_code=303)


@router.post("/prompts/{prompt_id}/reset")
async def reset_prompt_item(
    prompt_id: uuid.UUID,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Resets a customized prompt template back to system default."""
    from app.models.prompt_library import PromptLibraryItem
    from app.prompt_library import DEFAULT_PROMPT_REGISTRY

    item = (await db.execute(select(PromptLibraryItem).where(PromptLibraryItem.id == prompt_id))).scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Prompt item not found")

    for reg in DEFAULT_PROMPT_REGISTRY:
        if reg["key"] == item.key:
            item.template_content = reg["template_content"]
            item.is_customized = False
            item.updated_at = datetime.now(UTC)
            await db.commit()
            break

    return RedirectResponse(url="/admin/prompts", status_code=303)
