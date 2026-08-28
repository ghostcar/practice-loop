import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.encryption import encrypt_api_key, mask_api_key
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.client import check_llm_connection
from app.models.llm_config import LLMProviderConfig
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(prefix="/llm-configs", tags=["llm-configs"])


# --- Page ---


@router.get("/", response_class=HTMLResponse)
async def llm_configs_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manage LLM provider configurations."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    # Auto-seed Omniroute preset for new users (ADR-179).
    existing = await db.execute(select(LLMProviderConfig).where(LLMProviderConfig.user_id == user.id))
    if not existing.scalars().first():
        from app.seed import seed_llm_presets

        await seed_llm_presets(db, user_id=user.id)
        # Re-query after seeding
        pass

    result = await db.execute(
        select(LLMProviderConfig).where(LLMProviderConfig.user_id == user.id).order_by(LLMProviderConfig.provider_name)
    )
    configs = result.scalars().all()

    # Add masked keys for display
    configs_data = []
    for cfg in configs:
        configs_data.append(
            {
                "id": cfg.id,
                "provider_name": cfg.provider_name,
                "api_base_url": cfg.api_base_url,
                "api_key_masked": mask_api_key(cfg.api_key_encrypted),
                "model_name": cfg.model_name,
                "is_active": cfg.is_active,
                "llm_mode": cfg.llm_mode,
                "store_raw_response": cfg.store_raw_response,
                "total_tokens": cfg.total_tokens,
                "total_cost": cfg.total_cost,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="llm_configs.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "configs": configs_data,
        },
    )


@router.post("/check")
async def check_llm_config(
    api_base_url: str = Form(...),
    api_key: str = Form(default=""),
    model_name: str = Form(...),
    user: User = Depends(get_current_user),
):
    """Check provider connectivity without persisting the submitted key."""
    try:
        await check_llm_connection(api_base_url, api_key or None, model_name)
    except (RuntimeError, ValueError):
        return RedirectResponse(url="/llm-configs/?connection=failed", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/llm-configs/?connection=ok", status_code=status.HTTP_303_SEE_OTHER)


# --- CRUD ---


@router.post("/")
async def create_llm_config(
    request: Request,
    provider_name: str = Form(...),
    api_base_url: str = Form(...),
    api_key: str = Form(default=""),
    model_name: str = Form(...),
    llm_mode: str = Form(default="full"),
    store_raw_response: str = Form(default="true"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new LLM provider config."""
    from app.consent import has_consent

    if not await has_consent(db, user.id, "byok_provider"):
        return RedirectResponse(url="/consent/setup?required=byok_provider", status_code=status.HTTP_303_SEE_OTHER)
    try:
        await check_llm_connection(api_base_url, api_key or None, model_name)
    except (RuntimeError, ValueError):
        return RedirectResponse(url="/llm-configs/?connection=failed", status_code=status.HTTP_303_SEE_OTHER)

    encrypted = encrypt_api_key(api_key) if api_key else None
    # HTML form values: "true"/"false"/"on"/"1" accepted as True
    store_raw = store_raw_response.strip().lower() in {"true", "on", "1", "yes"}
    mode = llm_mode.strip().lower()
    if mode not in ("full", "abstract"):
        mode = "full"
    config = LLMProviderConfig(
        user_id=user.id,
        provider_name=provider_name.strip(),
        api_base_url=api_base_url.strip(),
        api_key_encrypted=encrypted,
        model_name=model_name.strip(),
        is_active=False,
        llm_mode=mode,
        store_raw_response=store_raw,
    )
    db.add(config)
    await db.flush()

    return RedirectResponse(url="/llm-configs/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{config_id}/update")
async def update_llm_config(
    request: Request,
    config_id: uuid.UUID,
    llm_mode: str = Form(default="full"),
    store_raw_response: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle llm_mode (full/abstract) and raw-response retention per config."""
    result = await db.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.id == config_id,
            LLMProviderConfig.user_id == user.id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    mode = llm_mode.strip().lower()
    if mode in ("full", "abstract"):
        config.llm_mode = mode
    # Checkbox absent from the form ⇒ unset ⇒ False; "1"/"on" ⇒ True
    config.store_raw_response = store_raw_response.strip().lower() in {"1", "on", "true", "yes"}
    db.add(config)
    await db.flush()

    return RedirectResponse(url="/llm-configs/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{config_id}/set-active")
async def set_active_config(
    request: Request,
    config_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set a specific config as the active one (deactivates others)."""
    # Deactivate all
    all_configs = await db.execute(select(LLMProviderConfig).where(LLMProviderConfig.user_id == user.id))
    for cfg in all_configs.scalars().all():
        cfg.is_active = cfg.id == config_id
        db.add(cfg)

    await db.flush()
    return RedirectResponse(url="/llm-configs/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{config_id}/delete")
async def delete_llm_config(
    request: Request,
    config_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an LLM provider config."""
    result = await db.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.id == config_id,
            LLMProviderConfig.user_id == user.id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    await db.delete(config)
    await db.flush()

    return RedirectResponse(url="/llm-configs/", status_code=status.HTTP_303_SEE_OTHER)
