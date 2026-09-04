"""Integration tests for Media Vault Security v2 and Voice TTS."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.telegram.voice_tts import synthesize_persona_voice_response


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
