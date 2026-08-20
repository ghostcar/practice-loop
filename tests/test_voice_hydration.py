"""Integration tests for Voice Log STT Auto-Hydration Engine."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.voice_hydration import parse_transcript_with_llm, process_voice_transcript_intake
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.telegram.agent_handler import handle_agent_voice_message


@pytest.mark.asyncio
async def test_parse_transcript_with_llm_heuristics():
    """Verify heuristic parsing extracts tasks and measurements."""
    transcript = "Выполнил зарядку, выпил 500мл воды и поспал 8 часов. Пропустил растяжку."
    parsed = await parse_transcript_with_llm(transcript)

    assert len(parsed["tasks_completed"]) >= 1
    assert len(parsed["tasks_interrupted"]) >= 1
    assert parsed["measurements"]["water_ml"] == 500.0
    assert parsed["measurements"]["sleep_hours"] == 8.0


@pytest.mark.asyncio
async def test_process_voice_transcript_intake_creates_logs(db_session: AsyncSession, test_user: User):
    """Verify processing transcript creates ActivityLog records in DB."""
    transcript = "Выполнил силовую тренировку, поспал 8 часов"
    res = await process_voice_transcript_intake(db_session, test_user, transcript)

    assert res["status"] == "success"
    assert res["logs_count"] >= 1
    assert "Голосовая заметка обработана" in res["summary_markdown"]

    # Verify ActivityLog in DB
    logs_res = await db_session.execute(select(ActivityLog).where(ActivityLog.user_id == test_user.id))
    logs = logs_res.scalars().all()
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_handle_agent_voice_message_handler(db_session: AsyncSession, test_user: User):
    """Verify telegram bot voice handler responds with summary markdown."""
    test_user.telegram_chat_id = 77665544
    await db_session.commit()

    mock_msg = MagicMock()
    mock_msg.chat.id = 77665544
    mock_msg.caption = "Выполнил вечернюю прогулку, выпил воды"
    mock_msg.bot.send_chat_action = AsyncMock()
    mock_msg.reply = AsyncMock()

    await handle_agent_voice_message(mock_msg, db=db_session)

    mock_msg.reply.assert_called_once()
    reply_text = mock_msg.reply.call_args[0][0]
    assert "Зафиксированные записи" in reply_text
