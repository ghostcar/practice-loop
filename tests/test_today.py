"""Tests for C4 — Today projection (единый экран дня, §10.1).

Страница /today объединяет сводки личных модулей (Tracker/Timer/Health/
Medication/Care/Aftercare/Journal/Training/Diet) без создания агрегированной
модели. View-level сшивка существующих сводок.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.models.aftercare import AftercareEntry
from app.models.journal import JournalEntry


@pytest.mark.asyncio
async def test_today_page_renders_empty(auth_client, test_user, db_session):
    resp = await auth_client.get("/today")
    assert resp.status_code == 200
    assert "Today" in resp.text or "Сегодня" in resp.text


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
