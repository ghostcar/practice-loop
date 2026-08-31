import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.encryption import decrypt_api_key, encrypt_api_key, mask_api_key
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.client import check_llm_connection
from app.models.llm_catalog import LLMGlobalModel, LLMGlobalProvider, LLMUserSelection
from app.models.llm_config import LLMProviderConfig
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(prefix="/llm-configs", tags=["llm-configs"])

# This router is registered at platform level: BYOK settings are available in
# tracker, timer, combined, and future product variants.


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

    global_result = await db.execute(
        select(LLMGlobalProvider).where(LLMGlobalProvider.enabled).order_by(LLMGlobalProvider.name)
    )
    global_providers = list(global_result.scalars().all())
    # Environment-backed portal providers are read-only metadata. Credentials
    # are never sent to templates or API responses.
    from app.llm.policy import available_sections, personal_llm_sections
    from app.llm.portal import get_portal_providers

    portal_providers = get_portal_providers()
    selection_result = await db.execute(select(LLMUserSelection).where(LLMUserSelection.user_id == user.id))
    selections = {selection.capability: selection for selection in selection_result.scalars().all()}

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
            "global_providers": global_providers,
            "portal_providers": portal_providers,
            "llm_sections": available_sections(),
            "personal_llm_sections": personal_llm_sections(),
            "selections": selections,
        },
    )


@router.get("/models")
async def list_provider_models(
    request: Request,
    provider_id: str | None = None,
    user_config_id: uuid.UUID | None = None,
    capability: str = "text",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return catalog models or models advertised by an owned BYOK provider.

    ``provider_id`` accepts either a UUID (global catalog provider) or a
    portal provider id (``portal:<n>:<name>``).
    """
    if capability not in {"text", "vision"}:
        raise HTTPException(status_code=400, detail="Invalid LLM capability")
    if bool(provider_id) == bool(user_config_id):
        raise HTTPException(status_code=400, detail="Exactly one provider is required")

    if provider_id and provider_id.startswith("portal:"):
        portal_id = provider_id
        from app.llm.portal import get_portal_providers

        portal_provider = next((item for item in get_portal_providers() if item.id == portal_id), None)
        if portal_provider is None:
            raise HTTPException(status_code=404, detail="Portal provider not found")
        models = [
            {"id": model.name, "name": model.name}
            for model in portal_provider.models
            if (capability == "text" and portal_provider.supports_text)
            or (capability == "vision" and model.supports_vision)
        ]
        return {"models": models}
    if provider_id:
        try:
            provider_uuid = uuid.UUID(provider_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid provider id") from None
        global_provider = await db.scalar(
            select(LLMGlobalProvider).where(LLMGlobalProvider.id == provider_uuid, LLMGlobalProvider.enabled)
        )
        if global_provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        result = await db.execute(
            select(LLMGlobalModel)
            .where(
                LLMGlobalModel.provider_id == provider_uuid,
                LLMGlobalModel.enabled,
                (LLMGlobalModel.supports_vision if capability == "vision" else LLMGlobalModel.supports_text),
            )
            .order_by(LLMGlobalModel.model_name)
        )
        return {"models": [{"id": str(model.id), "name": model.model_name} for model in result.scalars().all()]}

    config = await db.scalar(
        select(LLMProviderConfig).where(
            LLMProviderConfig.id == user_config_id,
            LLMProviderConfig.user_id == user.id,
        )
    )
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")
    from app.llm.client import list_llm_models

    try:
        names = await list_llm_models(
            config.api_base_url,
            decrypt_api_key(config.api_key_encrypted) if config.api_key_encrypted else None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Provider model list unavailable") from exc
    # BYOK capabilities cannot be inferred reliably from OpenAI-compatible IDs;
    # vision callers can still select only models returned by the provider.
    return {"models": [{"id": name, "name": name} for name in names]}


@router.post("/select")
async def select_llm_capability(
    capability: str = Form(...),
    model_name: str = Form(...),
    global_provider_id: uuid.UUID | None = Form(default=None),
    user_config_id: uuid.UUID | None = Form(default=None),
    portal_provider_id: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the user's text or vision provider/model selection."""
    if capability not in {"text", "vision"}:
        raise HTTPException(status_code=400, detail="Invalid LLM capability")
    if portal_provider_id and portal_provider_id.startswith("global:"):
        global_provider_id = uuid.UUID(portal_provider_id.removeprefix("global:"))
        portal_provider_id = None
    sources = [bool(global_provider_id), bool(user_config_id), bool(portal_provider_id)]
    if sum(sources) != 1:
        raise HTTPException(status_code=400, detail="Select exactly one provider source")
    if user_config_id:
        owned = await db.scalar(
            select(LLMProviderConfig.id).where(
                LLMProviderConfig.id == user_config_id,
                LLMProviderConfig.user_id == user.id,
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Config not found")
        from app.llm.policy import is_personal_allowed

        if not is_personal_allowed("assistant"):
            raise HTTPException(status_code=403, detail="Personal providers are disabled for this section")
    if portal_provider_id and portal_provider_id.startswith("portal:"):
        from app.llm.portal import get_portal_providers

        portal_provider = next((item for item in get_portal_providers() if item.id == portal_provider_id), None)
        if portal_provider is None:
            raise HTTPException(status_code=404, detail="Portal provider not found")
        model = next((item for item in portal_provider.models if item.name == model_name), None)
        model_unavailable = (
            model is None
            or (capability == "vision" and not model.supports_vision)
            or (capability == "text" and not portal_provider.supports_text)
        )
        if model_unavailable:
            raise HTTPException(status_code=400, detail="Model is not available for this capability")
    if global_provider_id and str(global_provider_id).startswith("portal:"):
        raise HTTPException(status_code=400, detail="Portal provider selection must use the portal provider field")
    if global_provider_id:
        provider = await db.scalar(
            select(LLMGlobalProvider).where(
                LLMGlobalProvider.id == global_provider_id,
                LLMGlobalProvider.enabled,
            )
        )
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        if capability == "vision" and not provider.supports_vision:
            raise HTTPException(status_code=400, detail="Provider does not support vision")
        if capability == "text" and not provider.supports_text:
            raise HTTPException(status_code=400, detail="Provider does not support text")
        valid_model = await db.scalar(
            select(LLMGlobalModel.id).where(
                LLMGlobalModel.provider_id == global_provider_id,
                LLMGlobalModel.model_name == model_name,
                LLMGlobalModel.enabled,
                (LLMGlobalModel.supports_vision if capability == "vision" else LLMGlobalModel.supports_text),
            )
        )
        if valid_model is None:
            raise HTTPException(status_code=400, detail="Model is not available for this capability")
    if user_config_id:
        owned = await db.scalar(
            select(LLMProviderConfig).where(
                LLMProviderConfig.id == user_config_id,
                LLMProviderConfig.user_id == user.id,
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Config not found")
        from app.llm.client import list_llm_models

        try:
            available = await list_llm_models(
                owned.api_base_url,
                decrypt_api_key(owned.api_key_encrypted) if owned.api_key_encrypted else None,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Provider model list unavailable") from exc
        if model_name not in available:
            raise HTTPException(status_code=400, detail="Model is not advertised by this provider")
    selection = await db.scalar(
        select(LLMUserSelection).where(
            LLMUserSelection.user_id == user.id,
            LLMUserSelection.capability == capability,
        )
    )
    if selection is None:
        selection = LLMUserSelection(user_id=user.id, capability=capability, model_name=model_name)
        db.add(selection)
    selection.global_provider_id = global_provider_id
    selection.user_config_id = user_config_id
    selection.portal_provider_id = portal_provider_id
    selection.model_name = model_name
    await db.flush()
    return RedirectResponse(url="/llm-configs/?selection=saved", status_code=status.HTTP_303_SEE_OTHER)


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

    return RedirectResponse(url="/llm-configs/?connection=saved", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{config_id}/update")
async def update_llm_config(
    request: Request,
    config_id: uuid.UUID,
    provider_name: str = Form(default=""),
    api_base_url: str = Form(default=""),
    api_key: str = Form(default=""),
    model_name: str = Form(default=""),
    llm_mode: str = Form(default="full"),
    store_raw_response: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit a config: credentials, model, llm_mode and raw-response retention.

    Empty api_key keeps the existing key; a new key is verified before saving.
    """
    result = await db.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.id == config_id,
            LLMProviderConfig.user_id == user.id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    name = provider_name.strip()
    base_url = api_base_url.strip()
    model = model_name.strip()
    new_key = api_key.strip()

    # When credentials or model change, re-verify the connection first.
    credentials_changed = (
        (base_url and base_url != config.api_base_url) or bool(new_key) or (model and model != config.model_name)
    )
    if credentials_changed:
        try:
            await check_llm_connection(
                base_url or config.api_base_url,
                new_key or (decrypt_api_key(config.api_key_encrypted) if config.api_key_encrypted else None),
                model or config.model_name,
            )
        except (RuntimeError, ValueError):
            return RedirectResponse(url="/llm-configs/?connection=failed", status_code=status.HTTP_303_SEE_OTHER)

    if name:
        config.provider_name = name
    if base_url:
        config.api_base_url = base_url
    if model:
        config.model_name = model
    if new_key:
        config.api_key_encrypted = encrypt_api_key(new_key)

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
