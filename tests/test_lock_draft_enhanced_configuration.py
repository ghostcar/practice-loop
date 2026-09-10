"""Tests for enhanced draft configuration and presets (ADR-203)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.locktimer_ui import _serialize_session
from app.locktimer import enums as e
from app.locktimer.services.drafts import create_draft, update_draft
from app.models.locktimer import LockSlotRule, LockTaskRule
from app.models.user import User

pytestmark = pytest.mark.anyio


class TestDraftEnhancedConfigurationService:
    async def test_create_draft_session_number_and_defaults(self, db_session: AsyncSession, test_user: User) -> None:
        """create_draft automatically computes sequential session_number and sets robust defaults."""
        d1 = await create_draft(db_session, owner_id=test_user.id, title="First Lock")
        assert d1.session_number == 1
        assert d1.title == "First Lock"
        assert d1.state == e.SESSION_DRAFT
        assert d1.can_extend_duration is False

        # Check default discipline policy
        assert d1.discipline_policy["penalty_time_minutes"] == 60
        assert d1.discipline_policy["penalty_points"] == 50
        assert d1.discipline_policy["escalation_multiplier"] == 1.5
        assert d1.discipline_policy["penalty_tasks_enabled"] is True
        assert "physical" in d1.discipline_policy["penalty_categories"]

        # Check extensions defaults
        assert d1.extensions_state["extensions_enabled"] is True
        assert d1.extensions_state["games"]["wheel_of_fortune"] is True
        assert d1.extensions_state["bad_luck_escalation_enabled"] is True

        # Check draft singleton: create_draft returns existing draft by default (ADR-204)
        same_draft = await create_draft(db_session, owner_id=test_user.id, title="Ignored")
        assert same_draft.id == d1.id

        # Once first session is started (active), next draft increments session_number
        d1.state = e.SESSION_ACTIVE
        await db_session.flush()

        d2 = await create_draft(db_session, owner_id=test_user.id, title="Second Lock")
        assert d2.session_number == 2
        assert d2.title == "Second Lock"

    async def test_update_draft_fields(self, db_session: AsyncSession, test_user: User) -> None:
        """update_draft successfully persists title and extensions state."""
        draft = await create_draft(db_session, owner_id=test_user.id)
        assert draft.session_number == 1

        new_ext = {"extensions_enabled": False, "games": {}}
        updated = await update_draft(
            db_session,
            draft,
            title="Upgraded Title",
            extensions_state=new_ext,
        )
        assert updated.title == "Upgraded Title"
        assert updated.extensions_state["extensions_enabled"] is False

    def test_serialize_session_display_name(self) -> None:
        """_serialize_session builds human-readable display names."""
        class MockSession:
            id = uuid.uuid4()
            title = "Weekend Challenge"
            session_number = 4
            device_id = None
            state = "draft"
            mode = "scheduled"
            duration_type = "duration_from_start"
            can_extend_duration = True
            current_tag_number = "TAG-101"
            discipline_policy = {}
            verification_required = True
            verification_frequency_hours = 8
            verification_mode = "ai_vision"
            pillory_enabled = True
            pillory_auto_extend = True
            extensions_state = {}
            is_frozen = False
            frozen_at = None
            frozen_remaining_seconds = None
            timezone = "Europe/Berlin"
            started_at = None
            effective_end_at = None
            original_end_at = datetime.now(UTC) + timedelta(days=3)
            max_end_at = datetime.now(UTC) + timedelta(days=7)

        serialized = _serialize_session(MockSession(), {})
        assert serialized["display_name"] == "Сессия #4: Weekend Challenge"
        assert serialized["session_number"] == 4
        assert serialized["title"] == "Weekend Challenge"
        assert serialized["verification_frequency_hours"] == 8
        assert serialized["max_duration_days"] >= 6


class TestDraftEnhancedHttpAPI:
    async def test_update_draft_via_http(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """POST /api/v2/locktimer/sessions/{id}/update handles all ADR-203 fields."""
        draft = await create_draft(db_session, owner_id=test_user.id)

        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{draft.id}/update",
            data={
                "title": "Autumn Solitude",
                "mode": "scheduled",
                "duration_days": "4",
                "duration_hours": "12",
                "max_duration_days": "10",
                "can_extend_duration": "true",
                "penalty_points": "80",
                "penalty_time_minutes": "45",
                "penalty_tasks_enabled": "true",
                "penalty_category_physical": "true",
                "penalty_category_reports": "true",
                "escalation_multiplier": "2.0",
                "verification_required": "true",
                "verification_frequency_hours": "6",
                "verification_mode": "community",
                "extensions_enabled": "true",
                "game_wheel_enabled": "true",
                "game_dice_enabled": "true",
                "bad_luck_escalation_enabled": "true",
                "pillory_enabled": "true",
                "pillory_auto_extend": "true",
                "pillory_extend_minutes": "20",
                "pillory_reduce_minutes": "10",
                "pillory_daily_cap_hours": "8",
            },
        )
        assert resp.status_code in (200, 303)

        await db_session.refresh(draft)
        assert draft.title == "Autumn Solitude"
        assert draft.can_extend_duration is True
        assert draft.verification_required is True
        assert draft.verification_frequency_hours == 6
        assert draft.verification_mode == "community"
        assert draft.pillory_enabled is True
        assert draft.pillory_auto_extend is True

        # Check discipline policy
        dp = draft.discipline_policy
        assert dp["penalty_points"] == 80
        assert dp["penalty_time_minutes"] == 45
        assert dp["escalation_multiplier"] == 2.0
        assert "physical" in dp["penalty_categories"]
        assert "reports" in dp["penalty_categories"]
        assert dp["pillory_settings"]["extend_minutes"] == 20
        assert dp["pillory_settings"]["reduce_minutes"] == 10
        assert dp["pillory_settings"]["daily_cap_hours"] == 8

        # Check extensions state
        es = draft.extensions_state
        assert es["extensions_enabled"] is True
        assert es["games"]["wheel_of_fortune"] is True
        assert es["games"]["dice_of_fate"] is True
        assert es["bad_luck_escalation_enabled"] is True

    async def test_add_slot_rule_with_presets_and_minutes(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """POST /api/v2/locktimer/sessions/{id}/slot-rules correctly parses minutes and human schedule."""
        draft = await create_draft(db_session, owner_id=test_user.id)

        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{draft.id}/slot-rules",
            data={
                "name": "🚿 Утренний душ",
                "rule_type": "every_n_days",
                "every_n_days": "2",
                "time_of_day": "08:30",
                "duration_minutes": "25",
                "max_late_minutes": "30",
                "allow_late_open": "true",
                "journal_auto": "true",
            },
        )
        assert resp.status_code in (200, 303)

        rules = (
            await db_session.execute(
                select(LockSlotRule).where(LockSlotRule.session_id == draft.id)
            )
        ).scalars().all()
        assert len(rules) == 1
        rule = rules[0]
        assert rule.name == "🚿 Утренний душ"
        assert rule.duration_seconds == 25 * 60
        assert rule.max_late_seconds == 30 * 60
        assert rule.schedule["n"] == 2
        assert rule.schedule["time_of_day"] == "08:30"
        assert rule.allow_late_open is True
        assert rule.journal_auto is True

    async def test_add_task_rule_with_presets_and_hours(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """POST /api/v2/locktimer/sessions/{id}/task-rules correctly parses hours and human schedule."""
        draft = await create_draft(db_session, owner_id=test_user.id)

        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{draft.id}/task-rules",
            data={
                "title": "🔍 Проверка замка и посадки",
                "schedule_type": "daily",
                "time_of_day": "11:00",
                "due_window_hours": "3",
                "requires_report": "true",
            },
        )
        assert resp.status_code in (200, 303)

        rules = (
            await db_session.execute(
                select(LockTaskRule).where(LockTaskRule.session_id == draft.id)
            )
        ).scalars().all()
        assert len(rules) == 1
        rule = rules[0]
        assert rule.title == "🔍 Проверка замка и посадки"
        assert rule.due_window_seconds == 3 * 3600
        assert rule.schedule["time_of_day"] == "11:00"
        assert rule.requires_report is True
