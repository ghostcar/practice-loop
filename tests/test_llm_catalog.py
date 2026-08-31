import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_catalog import LLMGlobalModel, LLMGlobalProvider, LLMUserSelection
from app.models.llm_config import LLMProviderConfig


@pytest.mark.asyncio
async def test_models_are_filtered_by_capability(auth_client: AsyncClient, db_session: AsyncSession):
    provider = LLMGlobalProvider(name="Catalog", api_base_url="https://example.test/v1", supports_vision=True)
    db_session.add(provider)
    await db_session.flush()
    db_session.add_all(
        [
            LLMGlobalModel(provider_id=provider.id, model_name="text-only", supports_text=True),
            LLMGlobalModel(
                provider_id=provider.id,
                model_name="vision-model",
                supports_text=True,
                supports_vision=True,
            ),
        ]
    )
    await db_session.flush()

    response = await auth_client.get(f"/llm-configs/models?provider_id={provider.id}&capability=vision")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["models"]] == ["vision-model"]


@pytest.mark.asyncio
async def test_user_selection_accepts_only_catalog_model(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    provider = LLMGlobalProvider(name="Catalog2", api_base_url="https://example.test/v1")
    db_session.add(provider)
    await db_session.flush()
    db_session.add(LLMGlobalModel(provider_id=provider.id, model_name="allowed", supports_text=True))
    await db_session.flush()

    response = await auth_client.post(
        "/llm-configs/select",
        data={
            "capability": "text",
            "global_provider_id": str(provider.id),
            "model_name": "allowed",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    selection = await db_session.scalar(select(LLMUserSelection).where(LLMUserSelection.user_id == test_user.id))
    assert selection is not None
    assert selection.model_name == "allowed"

    response = await auth_client.post(
        "/llm-configs/select",
        data={
            "capability": "text",
            "global_provider_id": str(provider.id),
            "model_name": "not-allowed",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_selection_cannot_use_another_users_config(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    other_config = LLMProviderConfig(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000099"),
        provider_name="Other",
        api_base_url="https://example.test/v1",
        model_name="other-model",
    )
    db_session.add(other_config)
    await db_session.flush()

    response = await auth_client.post(
        "/llm-configs/select",
        data={
            "capability": "text",
            "user_config_id": str(other_config.id),
            "model_name": "other-model",
        },
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert await db_session.scalar(select(LLMUserSelection).where(LLMUserSelection.user_id == test_user.id)) is None


@pytest.mark.asyncio
async def test_byok_models_endpoint_requires_ownership(auth_client: AsyncClient, db_session: AsyncSession):
    other_config = LLMProviderConfig(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000099"),
        provider_name="Other2",
        api_base_url="https://example.test/v1",
        model_name="other-model",
    )
    db_session.add(other_config)
    await db_session.flush()

    response = await auth_client.get(f"/llm-configs/models?user_config_id={other_config.id}&capability=text")
    assert response.status_code == 404
