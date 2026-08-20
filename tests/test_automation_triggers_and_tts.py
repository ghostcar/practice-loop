"""Integration tests for Automation Trigger Engine, Media Vault Security v2, and Voice TTS."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.automation_triggers import evaluate_user_triggers, generate_agent_automation_triggers
from app.models.activity_log import ActivityLog
from app.models.care import CareEntry
from app.models.user import User
from app.telegram.voice_tts import synthesize_persona_voice_response


@pytest.mark.asyncio
async def test_agent_history_analysis_creates_automation_triggers(db_session: AsyncSession, test_user: User):
    """Verify AI Agent analyzes history logs and auto-creates automation triggers."""
    log = ActivityLog(user_id=test_user.id, status="interrupted")
    db_session.add(log)

    care = CareEntry(user_id=test_user.id, entry_date=pytest.importorskip("datetime").date.today(), skin_reaction=2)
    db_session.add(care)
    await db_session.flush()

    res = await generate_agent_automation_triggers(db_session, test_user)
    assert res["status"] == "success"
    assert res["triggers_created_count"] >= 1

    actions = await evaluate_user_triggers(
        db_session, test_user, condition_type="missed_tasks_count", current_value=3.0
    )
    assert len(actions) >= 1
    assert actions[0]["action_type"] == "apply_penalty"


@pytest.mark.asyncio
async def test_one_time_media_token_burn_on_read(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    """Verify one-time media token burns immediately upon reading."""
    create_resp = await auth_client.post("/media/one-time-token", data={"media_path": "/uploads/proof.jpg"})
    assert create_resp.status_code == 200
    token_data = create_resp.json()
    token_code = token_data["token"]

    # First read - succeeds and burns
    view_resp = await auth_client.get(f"/media/view-once/{token_code}")
    assert view_resp.status_code == 200
    assert view_resp.json()["status"] == "burned"

    # Second read - fails with 404 (already burned)
    view_resp2 = await auth_client.get(f"/media/view-once/{token_code}")
    assert view_resp2.status_code == 404


@pytest.mark.asyncio
async def test_voice_tts_synthesis_helper():
    """Verify TTS synthesis generates voice note payload."""
    res = await synthesize_persona_voice_response(text="Выполни утренний чек-ин", persona_name="Строгая Гопота")
    assert res["status"] == "success"
    assert res["persona_name"] == "Строгая Гопота"
    assert res["simulated_duration_sec"] >= 1
