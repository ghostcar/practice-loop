import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.resolver import resolve_llm_config
from app.models.llm_catalog import LLMGlobalProvider, LLMUserSelection
from app.models.llm_config import LLMProviderConfig


@pytest.mark.asyncio
async def test_personal_selection_wins_for_capability(db_session: AsyncSession, test_user):
    config = LLMProviderConfig(
        user_id=test_user.id,
        provider_name="Personal Vision",
        api_base_url="https://personal.example/v1",
        model_name="vision-model",
        is_active=False,
    )
    db_session.add(config)
    await db_session.flush()
    db_session.add(
        LLMUserSelection(
            user_id=test_user.id,
            capability="vision",
            user_config_id=config.id,
            model_name=config.model_name,
        )
    )
    await db_session.flush()

    resolved = await resolve_llm_config(db_session, test_user.id, "vision")
    assert resolved is not None
    assert resolved.id == config.id


@pytest.mark.asyncio
async def test_portal_selection_uses_matching_personal_credentials(db_session: AsyncSession, test_user):
    provider = LLMGlobalProvider(name="Portal", api_base_url="https://portal.example/v1")
    db_session.add(provider)
    await db_session.flush()
    config = LLMProviderConfig(
        user_id=test_user.id,
        provider_name="Portal BYOK",
        api_base_url=provider.api_base_url,
        model_name="portal-text",
        is_active=False,
    )
    db_session.add(config)
    await db_session.flush()
    db_session.add(
        LLMUserSelection(
            user_id=test_user.id,
            capability="text",
            global_provider_id=provider.id,
            model_name=config.model_name,
        )
    )
    await db_session.flush()

    resolved = await resolve_llm_config(db_session, test_user.id, "text")
    assert resolved is not None
    assert resolved.id == config.id


@pytest.mark.asyncio
async def test_portal_selection_does_not_read_another_users_credentials(db_session: AsyncSession, test_user):
    provider = LLMGlobalProvider(name="Private Portal", api_base_url="https://private.example/v1")
    db_session.add(provider)
    await db_session.flush()
    db_session.add(
        LLMUserSelection(
            user_id=test_user.id,
            capability="text",
            global_provider_id=provider.id,
            model_name="model",
        )
    )
    other = LLMProviderConfig(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000099"),
        provider_name="Other",
        api_base_url=provider.api_base_url,
        model_name="model",
        is_active=True,
    )
    db_session.add(other)
    await db_session.flush()

    assert await resolve_llm_config(db_session, test_user.id, "text") is None
