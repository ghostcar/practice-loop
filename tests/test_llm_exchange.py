"""Integration tests for External Model Exchange Hub ("Внешняя ИИ-модель")."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.session import ActivitySession
from app.models.user import User


@pytest.mark.asyncio
async def test_llm_exchange_page_auth(auth_client: AsyncClient):
    """GET /llm/exchange returns 200 OK for authenticated user."""
    resp = await auth_client.get("/llm/exchange")
    assert resp.status_code == 200
    assert "Обмен с внешней ИИ-моделью" in resp.text


@pytest.mark.asyncio
async def test_export_cross_domain_prompt(auth_client: AsyncClient):
    """POST /llm/exchange/export returns prompt with requested domains."""
    resp = await auth_client.post(
        "/llm/exchange/export",
        data={"domains": ["tracker", "timer", "care"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "Сгенерируй согласованный план активностей" in data["prompt"]
    assert "Задачи и Активности" in data["prompt"]


@pytest.mark.asyncio
async def test_parse_external_llm_markdown_json(auth_client: AsyncClient):
    """POST /llm/exchange/parse parses raw text wrapped in markdown json block."""
    raw_markdown = """
```json
{
  "title": "План от Внешней Модели",
  "reasoning": "Тестовое обоснование подбора",
  "items": [
    {
      "domain": "tracker",
      "title": "Вечерний массаж",
      "duration_minutes": 15,
      "notes": "Выполнять в спокойной обстановке"
    }
  ]
}
```
"""
    resp = await auth_client.post(
        "/llm/exchange/parse",
        data={"raw_response": raw_markdown},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["parsed"]["title"] == "План от Внешней Модели"
    assert len(data["parsed"]["items"]) == 1


@pytest.mark.asyncio
async def test_confirm_hydrated_plan_creation(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    """POST /llm/exchange/confirm creates ActivitySession and ActivityLogs."""
    items_json = '[{"title": "Медитация и растяжка", "domain": "training", "notes": "30 минут"}]'
    resp = await auth_client.post(
        "/llm/exchange/confirm",
        data={
            "title": "Индивидуальный план",
            "reasoning": "Сгенерировано вручную через внешнюю модель",
            "items_json": items_json,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/sessions"

    # Verify ActivitySession was saved
    sess_res = await db_session.execute(
        select(ActivitySession).where(
            ActivitySession.owner_id == test_user.id,
            ActivitySession.title == "Индивидуальный план",
        )
    )
    sess = sess_res.scalar_one_or_none()
    assert sess is not None

    # Verify ActivityLog was created
    log_res = await db_session.execute(select(ActivityLog).where(ActivityLog.session_id == sess.id))
    logs = log_res.scalars().all()
    assert len(logs) == 1
    assert logs[0].selected_entity_name == "Медитация и растяжка"
