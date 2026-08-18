"""Tests for C4 — Today projection (единый экран дня, §10.1).

Страница /today объединяет сводки личных модулей (Tracker/Timer/Health/
Medication/Care/Aftercare/Journal/Training/Diet) без создания агрегированной
модели. View-level сшивка существующих сводок.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.activity_log import ActivityLog
from app.models.aftercare import AftercareEntry
from app.models.journal import JournalEntry


@pytest.mark.asyncio
async def test_today_page_renders_empty(auth_client, test_user, db_session):
    resp = await auth_client.get("/today")
    assert resp.status_code == 200
    assert "Today" in resp.text or "Сегодня" in resp.text
    assert 'id="pl-sidebar"' in resp.text
    assert 'href="/account"' in resp.text
    assert 'href="/login"' not in resp.text


@pytest.mark.asyncio
async def test_today_page_with_data(auth_client, test_user, db_session):
    db_session.add(JournalEntry(user_id=test_user.id, entry_date=date(2026, 8, 17), activity_type="massage"))
    db_session.add(AftercareEntry(user_id=test_user.id, entry_date=date(2026, 8, 17), kind="rest"))
    await db_session.flush()

    resp = await auth_client.get("/today")
    assert resp.status_code == 200
    # journal + aftercare summaries present
    body = resp.text
    assert "Journal" in body or "Журнал" in body
    assert "Aftercare" in body


@pytest.mark.asyncio
async def test_today_prioritizes_overdue_and_review_tasks(auth_client, test_user, db_session):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            ActivityLog(
                user_id=test_user.id,
                status="planned",
                selected_entity_name="Overdue task",
                scheduled_at=now - timedelta(days=2),
            ),
            ActivityLog(user_id=test_user.id, status="review_needed", selected_entity_name="Decision task"),
            ActivityLog(
                user_id=test_user.id,
                status="completed",
                selected_entity_name="Finished old task",
                scheduled_at=now - timedelta(days=2),
            ),
        ]
    )
    await db_session.flush()

    response = await auth_client.get("/today")
    assert response.status_code == 200
    assert "Needs attention" in response.text
    assert "Overdue task" in response.text
    assert "Decision task" in response.text
    assert "Finished old task" not in response.text
    assert 'href="/tasks/?attention=true"' in response.text

    filtered = await auth_client.get("/tasks/?attention=true")
    assert filtered.status_code == 200
    assert "Overdue task" in filtered.text
    assert "Decision task" in filtered.text
    assert "Finished old task" not in filtered.text
