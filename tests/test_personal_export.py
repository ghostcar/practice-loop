"""Complete owner-scoped Personal data export manifest."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.auth import hash_password
from app.models.activity_log import ActivityLog
from app.models.aftercare import AftercareEntry
from app.models.session import ActivitySession
from app.models.session_history import ActivitySessionHistory
from app.models.user import User


@pytest.mark.asyncio
async def test_personal_export_is_complete_unbounded_and_owner_scoped(auth_client, db_session, test_user):
    other = User(email="export-other@example.com", password_hash=hash_password("secret123"))
    db_session.add(other)
    await db_session.flush()
    db_session.add_all(
        [ActivityLog(user_id=test_user.id, selected_entity_name=f"Task {index}") for index in range(205)]
        + [ActivityLog(user_id=other.id, selected_entity_name="Foreign secret")]
        + [AftercareEntry(user_id=test_user.id, entry_date=date.today(), kind="rest")]
    )
    session = ActivitySession(owner_id=test_user.id, status="created")
    db_session.add(session)
    await db_session.flush()
    db_session.add(ActivitySessionHistory(session_id=session.id, actor_id=test_user.id, event_type="created"))
    await db_session.flush()

    response = await auth_client.get("/privacy/export")
    assert response.status_code == 200
    payload = json.loads(response.text)
    assert payload["schema_version"] == 2
    assert payload["counts"]["activity_logs"] == 205
    assert payload["counts"]["aftercare_entries"] == 1
    assert payload["counts"]["activity_sessions"] == 1
    assert payload["counts"]["activity_session_history"] == 1
    for section in (
        "attachments",
        "chastity_check_ins",
        "chastity_device_events",
        "task_body_targets",
        "task_inventory_usages",
        "task_location_usages",
        "task_locations",
        "care_course_sessions",
        "care_entry_products",
        "care_routine_products",
        "lock_timer_templates",
    ):
        assert section in payload["sections"]
    assert "Foreign secret" not in response.text
    assert "password_hash" not in response.text
    assert "api_key_encrypted" not in response.text
    assert "file_path" not in response.text
