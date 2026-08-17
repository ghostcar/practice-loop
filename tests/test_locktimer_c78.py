"""Tests for LockTimer C7+C8 — LLM proposals API and Timer UI pages."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import enums as e
from app.locktimer.llm_context import format_timer_prompt
from app.locktimer.services.execution import add_slot_rule, add_task_rule, create_draft, start_session
from app.models.locktimer import LockLlmProposal
from app.models.user import User

pytestmark = pytest.mark.anyio

FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


class TestLlmContext:
    """C7 — timer-aware context builder and prompt formatter."""

    async def test_format_timer_prompt_produces_string(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id, timezone_str="Europe/Moscow")
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Morning slot",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "09:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
        )
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="Daily report",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
        )
        started = await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        assert started.state == e.SESSION_ACTIVE

        from app.locktimer.llm_context import build_timer_context

        ctx = await build_timer_context(db_session, session.id, test_user.id)
        prompt = format_timer_prompt(ctx, "Make it harder")
        assert isinstance(prompt, str)
        assert "Morning slot" in prompt
        assert "Daily report" in prompt
        assert "Make it harder" in prompt
        assert "duration_from_start" in prompt

    async def test_context_fails_for_wrong_owner(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.llm_context import build_timer_context

        with pytest.raises(ValueError, match="not found"):
            await build_timer_context(db_session, uuid.uuid4(), test_user.id)


class TestLlmProposalModel:
    """C7 — LockLlmProposal ORM model."""

    async def test_create_proposal(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        proposal = LockLlmProposal(
            session_id=session.id,
            owner_id=test_user.id,
            kind="pre_start_plan",
            user_brief="Test brief",
            items=[
                {"item_id": "i1", "type": "slot_rule", "title": "New slot", "data": {}, "status": "pending"},
                {"item_id": "i2", "type": "task_rule", "title": "New task", "data": {}, "status": "pending"},
            ],
        )
        db_session.add(proposal)
        await db_session.flush()

        result = await db_session.execute(select(LockLlmProposal).where(LockLlmProposal.session_id == session.id))
        saved = result.scalar_one()
        assert saved.kind == "pre_start_plan"
        assert len(saved.items) == 2
        assert saved.status == "pending"

    async def test_proposal_cross_user_isolation(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        proposal = LockLlmProposal(
            session_id=session.id,
            owner_id=test_user.id,
            kind="pre_start_plan",
            items=[],
        )
        db_session.add(proposal)
        await db_session.flush()

        # Other user's query returns nothing
        other_id = uuid.uuid4()
        result = await db_session.execute(select(LockLlmProposal).where(LockLlmProposal.owner_id == other_id))
        assert result.scalar_one_or_none() is None


class TestTimerPages:
    """C8 — SSR timer pages."""

    async def test_overview_renders(self, auth_client, test_user: User) -> None:
        response = await auth_client.get("/locktimer")
        assert response.status_code == 200
        assert "Timer" in response.text
        assert "No active chastity session" in response.text

    async def test_overview_requires_auth(self, async_client) -> None:
        response = await async_client.get("/locktimer")
        assert response.status_code in (401, 403, 302)

    async def test_session_detail_redirects_for_missing(self, auth_client, test_user: User) -> None:
        random_id = uuid.uuid4()
        response = await auth_client.get(f"/locktimer/sessions/{random_id}", follow_redirects=False)
        assert response.status_code == 303
        assert "/locktimer" in response.headers.get("location", "")

    async def test_active_session_shows_on_overview(
        self, db_session: AsyncSession, auth_client, test_user: User
    ) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Daily",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)

        response = await auth_client.get("/locktimer")
        assert response.status_code == 200
        assert "Active" in response.text
        assert "duration_from_start" in response.text

    async def test_session_detail_page(self, db_session: AsyncSession, auth_client, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Morning check",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "09:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
        )
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="Drink water",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "10:00"},
            due_window_seconds=3600,
        )
        _started = await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)

        response = await auth_client.get(f"/locktimer/sessions/{session.id}")
        assert response.status_code == 200
        assert "active" in response.text.lower()
        assert "Morning check" in response.text
        assert "Drink water" in response.text
