"""Tests for Step 8 — LockTimer device inventory (ADR-076).

Covers:
1. Device helpers — get_device ownership/archived filtering, set_device_status.
2. Draft — create/update with device_id, foreign device rejected, unbind.
3. Lifecycle — start marks device in_use; safety-stop marks it available.
4. API — update-draft device_id form (set/clear/bad uuid), POST /locktimer/new.
5. UI — session detail renders device selector + bound device chip.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import enums as e
from app.locktimer.services.device import get_device, set_device_status
from app.locktimer.services.drafts import create_draft, update_draft
from app.locktimer.services.session import safety_stop, start_session
from app.models.life import InventoryItem
from app.models.locktimer import LockSession
from app.models.user import User

pytestmark = pytest.mark.anyio

FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _make_device(db: AsyncSession, user: User, status: str = "available") -> InventoryItem:
    item = InventoryItem(
        user_id=user.id,
        category="wearable",
        name="Steel cage",
        quantity=1,
        quantity_needed=1,
        is_shopping_list=False,
        status="bought",
        inventory_status=status,
    )
    db.add(item)
    return item


async def _startable_draft(db: AsyncSession, user: User, device_id: uuid.UUID | None) -> LockSession:
    return await create_draft(db, owner_id=user.id, timezone_str="UTC", device_id=device_id)


# ── Device helpers ───────────────────────────────────────────────────────────


class TestDeviceHelpers:
    async def test_get_device_owned(self, db_session: AsyncSession, test_user: User) -> None:
        dev = _make_device(db_session, test_user)
        await db_session.flush()
        found = await get_device(db_session, dev.id, test_user.id)
        assert found is not None
        assert found.name == "Steel cage"

    async def test_get_device_foreign(self, db_session: AsyncSession, test_user: User) -> None:
        other = User(email="other@example.com", password_hash="x", locale="en", theme="light")
        db_session.add(other)
        await db_session.flush()
        dev = _make_device(db_session, other)
        await db_session.flush()
        assert await get_device(db_session, dev.id, test_user.id) is None

    async def test_get_device_archived(self, db_session: AsyncSession, test_user: User) -> None:
        dev = _make_device(db_session, test_user, status="archived")
        await db_session.flush()
        assert await get_device(db_session, dev.id, test_user.id) is None

    async def test_set_device_status(self, db_session: AsyncSession, test_user: User) -> None:
        dev = _make_device(db_session, test_user)
        await db_session.flush()
        ok = await set_device_status(db_session, dev.id, test_user.id, "in_use")
        assert ok is True
        await db_session.flush()
        await db_session.refresh(dev)
        assert dev.inventory_status == "in_use"

    async def test_set_device_status_no_device(self, db_session: AsyncSession, test_user: User) -> None:
        assert await set_device_status(db_session, None, test_user.id, "in_use") is False
        assert await set_device_status(db_session, uuid.uuid4(), test_user.id, "in_use") is False


# ── Draft binding ────────────────────────────────────────────────────────────


class TestDraftDevice:
    async def test_create_draft_with_device(self, db_session: AsyncSession, test_user: User) -> None:
        dev = _make_device(db_session, test_user)
        await db_session.flush()
        session = await create_draft(db_session, owner_id=test_user.id, device_id=dev.id)
        assert session.device_id == dev.id

    async def test_create_draft_foreign_device_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        other = User(email="other@example.com", password_hash="x", locale="en", theme="light")
        db_session.add(other)
        await db_session.flush()
        dev = _make_device(db_session, other)
        await db_session.flush()
        with pytest.raises(ValueError):
            await create_draft(db_session, owner_id=test_user.id, device_id=dev.id)

    async def test_update_draft_set_and_clear_device(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        dev = _make_device(db_session, test_user)
        await db_session.flush()

        await update_draft(db_session, session, device_id=dev.id)
        assert session.device_id == dev.id

        # Explicit unbind (None) clears the device.
        await update_draft(db_session, session, device_id=None)
        assert session.device_id is None

    async def test_update_draft_foreign_device_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        other = User(email="other@example.com", password_hash="x", locale="en", theme="light")
        db_session.add(other)
        await db_session.flush()
        dev = _make_device(db_session, other)
        await db_session.flush()
        with pytest.raises(ValueError):
            await update_draft(db_session, session, device_id=dev.id)

    async def test_update_draft_requires_draft_state(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        dev = _make_device(db_session, test_user)
        await db_session.flush()
        with pytest.raises(ValueError):
            await update_draft(db_session, session, device_id=dev.id)


# ── Lifecycle: start → in_use, safety-stop → available ──────────────────────


class TestDeviceLifecycle:
    async def test_start_marks_device_in_use(self, db_session: AsyncSession, test_user: User) -> None:
        dev = _make_device(db_session, test_user, status="available")
        await db_session.flush()
        session = await _startable_draft(db_session, test_user, dev.id)

        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        await db_session.flush()
        await db_session.refresh(dev)
        assert dev.inventory_status == "in_use"

    async def test_safety_stop_marks_device_available(self, db_session: AsyncSession, test_user: User) -> None:
        dev = _make_device(db_session, test_user, status="available")
        await db_session.flush()
        session = await _startable_draft(db_session, test_user, dev.id)
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        await db_session.refresh(dev)
        assert dev.inventory_status == "in_use"

        await safety_stop(
            db_session, session_id=session.id, owner_id=test_user.id, reason_code="user_requested", now=FIXED_NOW
        )
        await db_session.flush()
        await db_session.refresh(dev)
        assert dev.inventory_status == "available"

    async def test_start_without_device_is_fine(self, db_session: AsyncSession, test_user: User) -> None:
        session = await _startable_draft(db_session, test_user, None)
        started = await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        assert started.state == e.SESSION_ACTIVE

    async def test_deleted_device_does_not_break_start(self, db_session: AsyncSession, test_user: User) -> None:
        # device_id points at a non-existent item (SET NULL in prod) — must not crash.
        session = await create_draft(db_session, owner_id=test_user.id, timezone_str="UTC")
        session.device_id = uuid.uuid4()
        await db_session.flush()
        started = await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        assert started.state == e.SESSION_ACTIVE


# ── API ──────────────────────────────────────────────────────────────────────


class TestDeviceApi:
    async def test_update_draft_form_sets_device(self, auth_client, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        dev = _make_device(db_session, test_user)
        await db_session.flush()

        response = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/update",
            data={"device_id": str(dev.id)},
        )
        assert response.status_code == 303
        await db_session.refresh(session)
        assert session.device_id == dev.id

    async def test_update_draft_form_clears_device(
        self, auth_client, db_session: AsyncSession, test_user: User
    ) -> None:
        dev = _make_device(db_session, test_user)
        await db_session.flush()
        session = await create_draft(db_session, owner_id=test_user.id, device_id=dev.id)

        response = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/update",
            data={"device_id": "__none__"},
        )
        assert response.status_code == 303
        await db_session.refresh(session)
        assert session.device_id is None

    async def test_update_draft_form_bad_device_uuid(
        self, auth_client, db_session: AsyncSession, test_user: User
    ) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await db_session.flush()
        response = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/update",
            data={"device_id": "not-a-uuid"},
        )
        assert response.status_code == 422

    async def test_update_draft_form_foreign_device_400(
        self, auth_client, db_session: AsyncSession, test_user: User
    ) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        other = User(email="other@example.com", password_hash="x", locale="en", theme="light")
        db_session.add(other)
        await db_session.flush()
        dev = _make_device(db_session, other)
        await db_session.flush()
        response = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/update",
            data={"device_id": str(dev.id)},
        )
        assert response.status_code == 400

    async def test_new_session_with_device(self, auth_client, db_session: AsyncSession, test_user: User) -> None:
        dev = _make_device(db_session, test_user)
        await db_session.flush()
        response = await auth_client.post("/locktimer/new", data={"device_id": str(dev.id)})
        assert response.status_code == 303
        location = response.headers.get("location", "")
        session_id = uuid.UUID(location.rstrip("/").split("/")[-1])
        saved = await db_session.execute(select(LockSession).where(LockSession.id == session_id))
        assert saved.scalar_one().device_id == dev.id


# ── UI ───────────────────────────────────────────────────────────────────────


class TestDeviceUi:
    async def test_session_detail_shows_device_selector_and_chip(
        self, auth_client, db_session: AsyncSession, test_user: User
    ) -> None:
        dev = _make_device(db_session, test_user, status="available")
        await db_session.flush()
        session = await create_draft(db_session, owner_id=test_user.id, device_id=dev.id)

        response = await auth_client.get(f"/locktimer/sessions/{session.id}")
        assert response.status_code == 200
        html = response.text
        # Device selector contains the device option (selected).
        assert f'value="{dev.id}"' in html
        assert "selected" in html
        # Bound device chip shows the name.
        assert dev.name in html
