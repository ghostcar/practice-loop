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
from app.seed import seed_entities, seed_llm_presets
from app.seed_body_parts import seed_body_parts
from app.seed_categories import seed_categories
from app.seed_inventory_categories import seed_inventory_categories
from app.seed_locations import seed_locations
from app.templates_setup import templates

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
    """Seed entity catalog + activity categories — requires admin role."""
    await seed_categories(db)
    await seed_entities(db, owner_id=user.id)
    return RedirectResponse(url="/admin", status_code=303)


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
