"""Tests for LLM Provider Config CRUD."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_config import LLMProviderConfig


@pytest.mark.asyncio
async def test_llm_configs_page_is_registered(auth_client: AsyncClient):
    """User LLM settings stay available as a platform route."""
    response = await auth_client.get("/llm-configs/", follow_redirects=False)
    assert response.status_code == 200
    assert "Add Provider" in response.text
    assert 'href="/admin"' not in response.text


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


# ──── ADR-191: LLM call logs + stale portal id tolerance ────


@pytest.mark.asyncio
async def test_call_llm_writes_log_on_success(auth_client, test_user, db_session, monkeypatch):
    import app.llm.client as llm_client
    from app.models.llm_config import LLMCallLog, LLMProviderConfig

    cfg = LLMProviderConfig(user_id=test_user.id, provider_name="TestLLM", api_base_url="http://x/v1", model_name="m1")
    db_session.add(cfg)
    await db_session.flush()

    class FakeMsg:
        content = '{"ok": true}'
        tool_calls = None

    class FakeResp:
        choices = [type("C", (), {"message": FakeMsg()})()]
        usage = type("U", (), {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12})()

    class FakeCompletions:
        async def create(self, **kwargs):
            return FakeResp()

    class FakeClient:
        def __init__(self, *a, **kw):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

        async def close(self):
            pass

    monkeypatch.setattr(llm_client, "AsyncOpenAI", FakeClient)

    llm_client.set_call_meta(section="tests", purpose="unit")
    result = await llm_client.call_llm(cfg, "sys", "user", db=db_session, user_id=test_user.id)
    assert result["content"] == '{"ok": true}'

    logs = (await db_session.execute(select(LLMCallLog).where(LLMCallLog.user_id == test_user.id))).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.status == "ok"
    assert log.total_tokens == 12
    assert log.section == "tests"
    assert log.purpose == "unit"
    assert log.provider_name == "TestLLM"


@pytest.mark.asyncio
async def test_call_llm_writes_log_on_error(auth_client, test_user, db_session, monkeypatch):
    import app.llm.client as llm_client
    from app.models.llm_config import LLMCallLog, LLMProviderConfig

    cfg = LLMProviderConfig(user_id=test_user.id, provider_name="BadLLM", api_base_url="http://x/v1", model_name="m1")
    db_session.add(cfg)
    await db_session.flush()

    class FakeCompletions:
        async def create(self, **kwargs):
            raise RuntimeError("connection refused")

    class FakeClient:
        def __init__(self, *a, **kw):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

        async def close(self):
            pass

    monkeypatch.setattr(llm_client, "AsyncOpenAI", FakeClient)

    with pytest.raises(RuntimeError):
        await llm_client.call_llm(cfg, "sys", "user", db=db_session, user_id=test_user.id)

    logs = (await db_session.execute(select(LLMCallLog).where(LLMCallLog.user_id == test_user.id))).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.status == "error"
    assert "connection refused" in (log.error_message or "")


@pytest.mark.asyncio
async def test_llm_logs_page_and_json(auth_client, test_user, db_session):
    from app.models.llm_config import LLMCallLog

    db_session.add(
        LLMCallLog(
            user_id=test_user.id,
            provider_name="P",
            model_name="m",
            status="error",
            error_message="boom",
            section="tasks",
            purpose="task_generation",
            total_tokens=0,
        )
    )
    await db_session.flush()

    page = await auth_client.get("/llm-configs/logs")
    assert page.status_code == 200
    assert "Журнал вызовов LLM" in page.text or "LLM Call Logs" in page.text
    assert "boom" in page.text

    js = await auth_client.get("/llm-configs/logs/json?status_filter=error")
    assert js.status_code == 200
    data = js.json()
    assert data["status"] == "ok"
    assert any(entry["error_message"] == "boom" for entry in data["logs"])

    js_all = await auth_client.get("/llm-configs/logs/json?status_filter=ok")
    assert all(entry["status"] == "ok" for entry in js_all.json()["logs"])

    # JSON parity under /api/v2
    js_v2 = await auth_client.get("/api/v2/llm/logs?status_filter=error")
    assert js_v2.status_code == 200
    assert js_v2.json()["status"] == "ok"
    assert any(entry["error_message"] == "boom" for entry in js_v2.json()["logs"])


def test_portal_config_stale_id_fallback():
    from app.llm.portal import get_portal_providers
    from app.llm.resolver import _portal_config_from_env

    providers = get_portal_providers()
    if not providers:
        pytest.skip("No portal providers configured in test env")
    first = providers[0]
    stale_id = f"{first.id} (local)"
    cfg = _portal_config_from_env(stale_id, first.models[0].name if first.models else "m")
    assert cfg is not None
    assert cfg.provider_name == first.name


# ──── Admin LLM pool page (ADR-191 regression) ────


async def _seed_global_provider(db_session) -> None:
    from app.models.llm_catalog import LLMGlobalModel, LLMGlobalProvider

    provider = LLMGlobalProvider(name="Test Portal AI", api_base_url="http://portal.local/v1")
    db_session.add(provider)
    await db_session.flush()
    db_session.add(LLMGlobalModel(provider_id=provider.id, model_name="auto", supports_text=True))
    await db_session.flush()


@pytest.mark.asyncio
async def test_admin_llm_pool_page_renders(auth_client, test_user, db_session):
    """/admin/llm-pool рендерит провайдеров и модели (MissingGreenlet регрессия)."""
    test_user.role = "admin"
    db_session.add(test_user)
    await db_session.flush()
    await _seed_global_provider(db_session)

    resp = await auth_client.get("/admin/llm-pool")
    assert resp.status_code == 200, resp.text[:300]
    assert "Test Portal AI" in resp.text
    assert "auto" in resp.text


@pytest.mark.asyncio
async def test_admin_llm_pool_forbidden_for_regular_user(auth_client, test_user, db_session):
    """Обычный пользователь не видит админский LLM-пул (403)."""
    resp = await auth_client.get("/admin/llm-pool")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_llm_pool_duplicate_provider_message(auth_client, test_user, db_session):
    """Ошибка дубликата имени провайдера показывается на странице."""
    test_user.role = "admin"
    db_session.add(test_user)
    await db_session.flush()
    await _seed_global_provider(db_session)

    # Сообщение об ошибке рендерится из query-параметра
    page = await auth_client.get("/admin/llm-pool?error=duplicate")
    assert page.status_code == 200
    assert "уже существует" in page.text or "already exists" in page.text

    # POST дубликата → 303 + error-параметр (последним: rollback в обработчике
    # откатывает общую тестовую транзакцию)
    resp = await auth_client.post(
        "/admin/llm-pool/providers",
        data={"name": "Test Portal AI", "api_base_url": "http://other.local/v1"},
    )
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/admin/llm-pool?error=duplicate"
