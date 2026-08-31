"""Resolve the effective LLM configuration for a user and capability."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import encrypt_api_key
from app.llm.policy import personal_allowed_for_runtime
from app.llm.portal import get_portal_providers
from app.models.llm_catalog import LLMGlobalModel, LLMGlobalProvider, LLMUserSelection
from app.models.llm_config import LLMProviderConfig


def _portal_config_from_env(portal_id: str, model_name: str) -> LLMProviderConfig | None:
    """Build an in-memory LLMProviderConfig from an env-backed portal provider.

    The env key is encrypted into ``api_key_encrypted`` so downstream callers
    that decrypt it (call_llm) work unchanged. The object is not persisted.
    """
    provider = next((p for p in get_portal_providers() if p.id == portal_id), None)
    if provider is None:
        return None
    cfg = LLMProviderConfig(
        provider_name=provider.name,
        api_base_url=provider.base_url,
        api_key_encrypted=encrypt_api_key(provider.api_key) if provider.api_key else None,
        model_name=model_name,
        is_active=True,
        llm_mode="full",
        store_raw_response=False,
    )
    return cfg


async def resolve_llm_config(
    db: AsyncSession,
    user_id: uuid.UUID,
    capability: str = "text",
    section: str = "assistant",
) -> LLMProviderConfig | None:
    """Return a runtime config for the user's personal or portal selection.

    Selection precedence (per capability):
    1. Personal BYOK config (``user_config_id``) — only when policy allows.
    2. DB-backed global provider (``global_provider_id``) — metadata from the
       admin catalog; credentials come from a matching personal config.
    3. Env-backed portal provider (``portal_provider_id``) — credentials read
       from the deployment environment; no DB row needed.
    4. Legacy active-config fallback.
    """
    if capability not in {"text", "vision"}:
        raise ValueError("capability must be text or vision")

    selection = await db.scalar(
        select(LLMUserSelection).where(
            LLMUserSelection.user_id == user_id,
            LLMUserSelection.capability == capability,
        )
    )
    if selection is not None:
        if selection.user_config_id and personal_allowed_for_runtime(section):
            return await db.scalar(
                select(LLMProviderConfig).where(
                    LLMProviderConfig.id == selection.user_config_id,
                    LLMProviderConfig.user_id == user_id,
                )
            )
        if selection.global_provider_id:
            provider = await db.scalar(
                select(LLMGlobalProvider).where(
                    LLMGlobalProvider.id == selection.global_provider_id,
                    LLMGlobalProvider.enabled,
                )
            )
            if provider is not None:
                # Portal metadata selects the provider; credentials remain
                # personal and must be explicitly attached by the user.
                return await db.scalar(
                    select(LLMProviderConfig).where(
                        LLMProviderConfig.user_id == user_id,
                        LLMProviderConfig.api_base_url == provider.api_base_url,
                    ).order_by(LLMProviderConfig.is_active.desc(), LLMProviderConfig.created_at.desc())
                )
        if selection.portal_provider_id:
            # Env-backed portal provider: use the deployment key directly.
            return _portal_config_from_env(selection.portal_provider_id, selection.model_name)

    legacy = await db.scalar(
        select(LLMProviderConfig).where(
            LLMProviderConfig.user_id == user_id,
            LLMProviderConfig.is_active.is_(True),
        ).order_by(LLMProviderConfig.created_at.desc())
    )
    if legacy is not None:
        return legacy

    return None


async def is_catalog_model_available(
    db: AsyncSession,
    provider_id: uuid.UUID,
    model_name: str,
    capability: str,
) -> bool:
    """Check a portal model's enabled capability without trusting form input."""
    if capability not in {"text", "vision"}:
        return False
    return (
        await db.scalar(
            select(LLMGlobalModel.id).where(
                LLMGlobalModel.provider_id == provider_id,
                LLMGlobalModel.model_name == model_name,
                LLMGlobalModel.enabled,
                (LLMGlobalModel.supports_vision if capability == "vision" else LLMGlobalModel.supports_text),
            )
        )
    ) is not None
