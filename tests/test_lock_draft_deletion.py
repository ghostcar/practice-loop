"""Tests for deleting draft lock sessions (ADR-202)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import enums as e
from app.locktimer.repositories import get_session
from app.locktimer.services.drafts import (
    add_slot_rule,
    add_task_rule,
    create_draft,
    delete_draft,
)
from app.locktimer.services.session import safety_stop, start_session
from app.models.life import InventoryItem
from app.models.locktimer import LockAuditEvent, LockSlotRule, LockTaskRule
from app.models.user import User

pytestmark = pytest.mark.anyio


class TestDraftDeletionService:
    async def test_delete_draft_success(self, db_session: AsyncSession, test_user: User) -> None:
        """Creating a draft, adding rules, then deleting it completely cleans it up."""
        draft = await create_draft(db_session, owner_id=test_user.id)
        session_id = draft.id

        slot = await add_slot_rule(
            db_session,
            session_id=session_id,
            name="Morning unlock",
            rule_type="fixed",
            schedule={"time": "08:00"},
            duration_seconds=900,
        )
        task = await add_task_rule(
            db_session,
            session_id=session_id,
            title="Clean cage",
            schedule_type="daily",
            schedule={"time": "09:00"},
            due_window_seconds=3600,
        )

        assert slot.id is not None
        assert task.id is not None

        # Call delete_draft
        await delete_draft(db_session, session_id=session_id, owner_id=test_user.id)

        # Verify session is deleted
        deleted_sess = await get_session(db_session, session_id, test_user.id)
        assert deleted_sess is None

        # Verify rules are deleted
        slot_res = await db_session.execute(select(LockSlotRule).where(LockSlotRule.session_id == session_id))
        assert len(slot_res.scalars().all()) == 0

        task_res = await db_session.execute(select(LockTaskRule).where(LockTaskRule.session_id == session_id))
        assert len(task_res.scalars().all()) == 0

        # Verify audit log was written
        audit_res = await db_session.execute(
            select(LockAuditEvent).where(
                LockAuditEvent.session_id == session_id,
                LockAuditEvent.event_type == "locktimer.session.draft_deleted",
            )
        )
        audit_entry = audit_res.scalar_one_or_none()
        assert audit_entry is not None
        assert audit_entry.actor_user_id == test_user.id

    async def test_delete_draft_releases_inventory_device(self, db_session: AsyncSession, test_user: User) -> None:
        """If an inventory item was associated with the draft, it remains available."""
        device = InventoryItem(
            user_id=test_user.id,
            name="Test Chastity Cage",
            category="device",
            group_type="equipment",
            inventory_status="available",
        )
        db_session.add(device)
        await db_session.flush()

        draft = await create_draft(db_session, owner_id=test_user.id, device_id=device.id)
        assert draft.device_id == device.id

        await delete_draft(db_session, session_id=draft.id, owner_id=test_user.id)

        await db_session.refresh(device)
        assert device.inventory_status == "available"

    async def test_cannot_delete_active_session(self, db_session: AsyncSession, test_user: User) -> None:
        """Active sessions cannot be deleted; they must go through safety-stop."""
        draft = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=draft.id,
            name="Unlock",
            rule_type="fixed",
            schedule={"time": "08:00"},
            duration_seconds=900,
        )
        # Start session
        active_session = await start_session(db_session, session_id=draft.id, owner_id=test_user.id)
        assert active_session.state == e.SESSION_ACTIVE

        with pytest.raises(ValueError, match="Only draft sessions can be deleted"):
            await delete_draft(db_session, session_id=active_session.id, owner_id=test_user.id)

    async def test_cannot_delete_safety_stopped_session(self, db_session: AsyncSession, test_user: User) -> None:
        """Sessions that underwent safety stop cannot be deleted (audit trail)."""
        draft = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=draft.id,
            name="Unlock",
            rule_type="fixed",
            schedule={"time": "08:00"},
            duration_seconds=900,
        )
        await start_session(db_session, session_id=draft.id, owner_id=test_user.id)
        stopped = await safety_stop(db_session, session_id=draft.id, owner_id=test_user.id)
        assert stopped.state == e.SESSION_SAFETY_STOPPED

        with pytest.raises(ValueError, match="Only draft sessions can be deleted"):
            await delete_draft(db_session, session_id=draft.id, owner_id=test_user.id)

    async def test_cannot_delete_other_user_draft(self, db_session: AsyncSession, test_user: User) -> None:
        """Users cannot delete other users' drafts."""
        other_user = User(
            email=f"other_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hash",
        )
        db_session.add(other_user)
        await db_session.flush()

        draft = await create_draft(db_session, owner_id=other_user.id)

        with pytest.raises(ValueError, match="Session not found"):
            await delete_draft(db_session, session_id=draft.id, owner_id=test_user.id)


class TestDraftDeletionAPI:
    async def test_api_delete_draft_post_browser_redirect(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Browser form POST /api/v2/locktimer/sessions/{id}/delete redirects to /locktimer."""
        draft = await create_draft(db_session, owner_id=test_user.id)
        session_id = str(draft.id)

        response = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == "/locktimer"

        # Verify it no longer exists
        sess = await get_session(db_session, draft.id, test_user.id)
        assert sess is None

    async def test_api_delete_draft_post_bearer_json(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Bearer API client POST /api/v2/locktimer/sessions/{id}/delete returns JSON status deleted."""
        from app.auth import create_access_token

        draft = await create_draft(db_session, owner_id=test_user.id)
        session_id = str(draft.id)
        token = create_access_token(test_user.id)

        response = await async_client.post(
            f"/api/v2/locktimer/sessions/{session_id}/delete",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "deleted"

        # Verify it no longer exists
        sess = await get_session(db_session, draft.id, test_user.id)
        assert sess is None

    async def test_api_delete_draft_rejects_active(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """POST /api/v2/locktimer/sessions/{id}/delete rejects deletion of active session with 400."""
        draft = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=draft.id,
            name="Unlock",
            rule_type="fixed",
            schedule={"time": "08:00"},
            duration_seconds=900,
        )
        await start_session(db_session, session_id=draft.id, owner_id=test_user.id)

        response = await auth_client.post(
            f"/api/v2/locktimer/sessions/{draft.id}/delete",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 400
        assert "Only draft sessions can be deleted" in response.text
