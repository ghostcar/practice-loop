"""Tests for LLM Provider Config CRUD."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_config import LLMProviderConfig


@pytest.mark.asyncio
async def test_create_llm_config(auth_client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch):
    """Add a new LLM provider config."""

    async def connection_ok(*args, **kwargs):
        return None

    monkeypatch.setattr("app.api.llm_configs.check_llm_connection", connection_ok)
    await auth_client.post(
        "/api/v2/consent",
        json={"consent_type": "byok_provider", "state": "granted"},
    )
    response = await auth_client.post(
        "/llm-configs/",
        data={
            "provider_name": "TestGroq",
            "api_base_url": "https://api.groq.com/openai/v1",
            "api_key": "gsk_test123",
            "model_name": "llama-3.3-70b",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.user_id == test_user.id,
            LLMProviderConfig.provider_name == "TestGroq",
        )
    )
    cfg = result.scalar_one_or_none()
    assert cfg is not None
    assert cfg.model_name == "llama-3.3-70b"
    assert not cfg.is_active
    assert cfg.api_key_encrypted is not None


@pytest.mark.asyncio
async def test_create_llm_config_does_not_persist_on_failed_check(
    auth_client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch
):
    async def connection_failed(*args, **kwargs):
        raise RuntimeError("LLM connection check failed")

    monkeypatch.setattr("app.api.llm_configs.check_llm_connection", connection_failed)
    await auth_client.post(
        "/api/v2/consent",
        json={"consent_type": "byok_provider", "state": "granted"},
    )
    response = await auth_client.post(
        "/llm-configs/",
        data={
            "provider_name": "Unavailable",
            "api_base_url": "https://provider.invalid/v1",
            "api_key": "secret-key",
            "model_name": "missing-model",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("connection=failed")
    result = await db_session.execute(select(LLMProviderConfig).where(LLMProviderConfig.user_id == test_user.id))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_set_active_config(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Set a config as active (should deactivate others)."""
    cfg1 = LLMProviderConfig(
        user_id=test_user.id,
        provider_name="Provider1",
        api_base_url="https://p1.example.com/v1",
        model_name="m1",
        is_active=True,
    )
    cfg2 = LLMProviderConfig(
        user_id=test_user.id,
        provider_name="Provider2",
        api_base_url="https://p2.example.com/v1",
        model_name="m2",
        is_active=False,
    )
    db_session.add_all([cfg1, cfg2])
    await db_session.flush()

    response = await auth_client.post(
        f"/llm-configs/{cfg2.id}/set-active",
        follow_redirects=False,
    )
    assert response.status_code == 303

    await db_session.refresh(cfg1)
    await db_session.refresh(cfg2)
    assert not cfg1.is_active
    assert cfg2.is_active


@pytest.mark.asyncio
async def test_delete_llm_config(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Delete an LLM provider config."""
    cfg = LLMProviderConfig(
        user_id=test_user.id,
        provider_name="ToDelete",
        api_base_url="https://del.example.com/v1",
        model_name="m1",
    )
    db_session.add(cfg)
    await db_session.flush()

    response = await auth_client.post(
        f"/llm-configs/{cfg.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303

    result = await db_session.execute(select(LLMProviderConfig).where(LLMProviderConfig.id == cfg.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_nonexistent_config(auth_client: AsyncClient):
    """Deleting a non-existent config returns 404."""
    response = await auth_client.post(
        f"/llm-configs/{uuid.uuid4()}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 404
