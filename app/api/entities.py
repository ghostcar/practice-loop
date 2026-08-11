import uuid
from datetime import UTC

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn
from app.models.user import User
from app.schemas.entity import DESIRE_LEVELS
from app.slugify import slugify
from app.templates_setup import templates

router = APIRouter(prefix="/entities", tags=["entities"])


# --- Pages ---


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    category: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Browse the entity catalog."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    query = select(Entity).where(Entity.is_public | (Entity.owner_id == user.id))
    if category:
        query = query.where(Entity.category == category)

    result = await db.execute(query.order_by(Entity.category, Entity.real_name))
    entities = result.scalars().all()

    # Get user's opt-ins
    opt_in_result = await db.execute(select(UserEntityOptIn).where(UserEntityOptIn.user_id == user.id))
    opt_ins = {oi.entity_id: oi for oi in opt_in_result.scalars().all()}

    # Gather unique categories
    cat_result = await db.execute(select(Entity.category).distinct().order_by(Entity.category))
    categories = [row[0] for row in cat_result.all()]

    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "entities": entities,
            "opt_ins": opt_ins,
            "categories": categories,
            "active_category": category,
            "desire_levels": DESIRE_LEVELS,
            "active_nav": "catalog",
        },
    )


@router.get("/my", response_class=HTMLResponse)
async def my_entities_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User's personal entities."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(
        select(Entity).where(Entity.owner_id == user.id).order_by(Entity.category, Entity.real_name)
    )
    entities = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="my_entities.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "entities": entities,
            "active_nav": "catalog",
        },
    )


# --- CRUD API ---


@router.post("/")
async def create_entity(
    request: Request,
    real_name: str = Form(...),
    type: str = Form(default="one_time"),
    category: str = Form(...),
    tags: str = Form(default=""),
    is_public: bool = Form(default=False),
    risk_level: str = Form(default="not_assessed"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new entity."""
    if type not in ("one_time", "series", "infinite"):
        type = "one_time"
    if risk_level not in ("not_assessed", "low", "elevated", "high"):
        risk_level = "not_assessed"
    entity = Entity(
        type=type,
        real_name=real_name.strip(),
        slug=slugify(real_name),
        category=category.strip(),
        tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else None,
        owner_id=user.id,
        is_public=is_public,
        author_id=user.id if is_public else None,
        risk_level=risk_level,
    )
    db.add(entity)
    await db.flush()

    referer = request.headers.get("referer", "/entities/my")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{entity_id}/publish")
async def publish_entity(
    request: Request,
    entity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish a personal entity (make it public)."""
    result = await db.execute(select(Entity).where(Entity.id == entity_id, Entity.owner_id == user.id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity.is_public = True
    entity.author_id = user.id
    db.add(entity)

    referer = request.headers.get("referer", "/entities/my")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{entity_id}/delete")
async def delete_entity(
    request: Request,
    entity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a personal entity."""
    result = await db.execute(select(Entity).where(Entity.id == entity_id, Entity.owner_id == user.id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    await db.delete(entity)

    referer = request.headers.get("referer", "/entities/my")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


# --- Opt-in API ---


@router.post("/{entity_id}/opt-in")
async def toggle_opt_in(
    request: Request,
    entity_id: uuid.UUID,
    is_opted_in: bool = Form(default=True),
    rating: int | None = Form(default=None),
    desire_level: str = Form(default="neutral"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set or update opt-in preference for an entity (public or owned only)."""
    # Verify entity exists AND is public or owned by user
    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user.id),
        )
    )
    if ent_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Upsert opt-in
    result = await db.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == user.id,
            UserEntityOptIn.entity_id == entity_id,
        )
    )
    opt_in = result.scalar_one_or_none()

    if opt_in is None:
        opt_in = UserEntityOptIn(
            user_id=user.id,
            entity_id=entity_id,
            is_opted_in=is_opted_in,
            rating=rating if 1 <= (rating or 0) <= 5 else None,
            desire_level=desire_level if desire_level in DESIRE_LEVELS else "neutral",
        )
    else:
        opt_in.is_opted_in = is_opted_in
        if rating is not None and 1 <= rating <= 5:
            opt_in.rating = rating
        if desire_level in DESIRE_LEVELS:
            opt_in.desire_level = desire_level

    from datetime import datetime

    opt_in.updated_at = datetime.now(UTC)
    db.add(opt_in)
    await db.flush()

    referer = request.headers.get("referer", "/entities/catalog")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)
