from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.seed import seed_entities, seed_llm_presets
from app.templates_setup import templates

router = APIRouter(prefix="/admin", tags=["admin"])


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
        },
    )


@router.post("/seed-entities")
async def seed_entities_endpoint(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Seed entity catalog — requires admin role."""
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
