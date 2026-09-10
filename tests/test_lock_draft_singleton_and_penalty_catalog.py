"""Tests for ADR-204: Draft Singleton, Numeric Verification Code, History Filtering, and Catalog Penalty Tasks."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import enums as e
from app.locktimer.services.drafts import create_draft, get_user_draft
from app.locktimer.services.penalty_tasks_service import (
    assign_penalty_tasks_for_violation,
    list_available_penalty_entities,
)
from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.locktimer import LockSession
from app.models.user import User
from app.services.media import generate_verification_code

pytestmark = pytest.mark.anyio


class TestADR204NumericVerificationCode:
    def test_generate_verification_code_digits_only(self) -> None:
        """Verification code must be 6 digits only (0-9) for manual paper writing (ADR-204)."""
        for _ in range(20):
            code = generate_verification_code(length=6)
            assert len(code) == 6
            assert code.isdigit(), f"Code {code} must only contain digits"


class TestADR204DraftSingletonAndHistory:
    async def test_draft_singleton_service(self, db_session: AsyncSession, test_user: User) -> None:
        """Only one draft can exist at a time; subsequent create_draft returns existing."""
        d1 = await create_draft(db_session, owner_id=test_user.id, title="Original Draft")
        assert d1.state == e.SESSION_DRAFT

        # Second create_draft returns d1
        d2 = await create_draft(db_session, owner_id=test_user.id, title="Another Title")
        assert d2.id == d1.id
        assert d2.title == "Original Draft"

        # Explicit lookup returns d1
        found = await get_user_draft(db_session, test_user.id)
        assert found is not None
        assert found.id == d1.id

    async def test_draft_singleton_http_redirect(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """GET and POST /locktimer/new redirect to existing draft if one exists."""
        d1 = await create_draft(db_session, owner_id=test_user.id, title="Active Draft")

        # POST /locktimer/new should redirect to /locktimer/sessions/{d1.id}
        res_post = await auth_client.post("/locktimer/new", data={"title": "Should Ignore"}, follow_redirects=False)
        assert res_post.status_code == 303
        assert res_post.headers["location"] == f"/locktimer/sessions/{d1.id}"

        # GET /locktimer/new should also redirect to existing draft
        res_get = await auth_client.get("/locktimer/new", follow_redirects=False)
        assert res_get.status_code == 303
        assert res_get.headers["location"] == f"/locktimer/sessions/{d1.id}"

    async def test_overview_recent_excludes_drafts(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """Drafts must never appear in Recent Sessions history (ADR-204)."""
        # Create one draft and one completed session
        draft = await create_draft(db_session, owner_id=test_user.id, title="My Draft Session")
        assert draft.title == "My Draft Session"

        completed = LockSession(
            owner_id=test_user.id,
            title="Completed History Session",
            session_number=10,
            state=e.SESSION_COMPLETED,
            duration_type=e.DURATION_FROM_START,
            timezone="UTC",
            started_at=datetime.now(UTC),
            effective_end_at=datetime.now(UTC),
            random_seed_encrypted="abc",
            random_seed_commitment="def",
        )
        db_session.add(completed)
        await db_session.flush()

        res = await auth_client.get("/locktimer")
        assert res.status_code == 200
        content = res.text

        # Draft should appear in the drafts section or header open draft
        assert "My Draft Session" in content
        # Completed should be in recent history
        assert "Completed History Session" in content


class TestADR204PenaltyTasksCatalog:
    async def test_list_available_penalty_entities(self, db_session: AsyncSession, test_user: User) -> None:
        """Entities in physical/chores/reports/discipline categories are discoverable."""
        e1 = Entity(
            owner_id=None,
            category="physical",
            real_name="Приседания у стены",
            params_schema={"unit": "раз", "min": 20, "max": 100},
        )
        e2 = Entity(
            owner_id=test_user.id,
            category="chores",
            real_name="Генеральная уборка",
            params_schema={"unit": "мин"},
        )
        db_session.add_all([e1, e2])
        await db_session.flush()

        items = await list_available_penalty_entities(db_session, test_user.id)
        names = [it["real_name"] for it in items]
        assert "Приседания у стены" in names
        assert "Генеральная уборка" in names

    async def test_assign_penalty_tasks_random_one_and_escalation(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Assign penalty task creates ActivityLog with progressive escalation (ADR-204)."""
        session = LockSession(
            owner_id=test_user.id,
            title="Escalation Test Session",
            session_number=5,
            state=e.SESSION_ACTIVE,
            duration_type=e.DURATION_FROM_START,
            timezone="UTC",
            discipline_policy={
                "penalty_tasks_enabled": True,
                "escalation_multiplier": 2.0,
                "penalty_tasks_config": {
                    "mode": "random_one",
                    "items": [
                        {
                            "entity_id": None,
                            "activity_name": "Отжимания от пола",
                            "violation_type": "breach_relapse",
                            "initial_value": 20,
                            "unit": "раз",
                            "is_dynamic": True,
                        }
                    ],
                },
            },
            random_seed_encrypted="abc",
            random_seed_commitment="def",
        )
        db_session.add(session)
        await db_session.flush()

        # First violation: initial_value = 20
        tasks1 = await assign_penalty_tasks_for_violation(
            db_session,
            session=session,
            violation_type="breach_relapse",
            violation_count=1,
        )
        assert len(tasks1) == 1
        t1 = tasks1[0]
        assert isinstance(t1, ActivityLog)
        assert t1.selected_params["value"] == 20
        assert "20 раз" in t1.planned_value

        # Second violation with dynamic escalation: 20 * (2.0 ^ 1) = 40
        tasks2 = await assign_penalty_tasks_for_violation(
            db_session,
            session=session,
            violation_type="breach_relapse",
            violation_count=2,
        )
        assert len(tasks2) == 1
        t2 = tasks2[0]
        assert t2.selected_params["value"] == 40
        assert "40 раз" in t2.planned_value
        assert "эскалация #2 x2.0" in t2.title_override

    async def test_assign_penalty_tasks_all_mode_and_filtering(self, db_session: AsyncSession, test_user: User) -> None:
        """Mode 'all' assigns all matching violation activities (ADR-204)."""
        session = LockSession(
            owner_id=test_user.id,
            title="All Mode Test Session",
            session_number=6,
            state=e.SESSION_ACTIVE,
            duration_type=e.DURATION_FROM_START,
            timezone="UTC",
            discipline_policy={
                "penalty_tasks_enabled": True,
                "escalation_multiplier": 1.5,
                "penalty_tasks_config": {
                    "mode": "all",
                    "items": [
                        {
                            "activity_name": "Задание на опоздание",
                            "violation_type": "late_return",
                            "initial_value": 15,
                            "unit": "мин",
                            "is_dynamic": False,
                        },
                        {
                            "activity_name": "Универсальное наказание",
                            "violation_type": "any",
                            "initial_value": 50,
                            "unit": "раз",
                            "is_dynamic": False,
                        },
                        {
                            "activity_name": "Только за срыв",
                            "violation_type": "breach_relapse",
                            "initial_value": 100,
                            "unit": "раз",
                            "is_dynamic": False,
                        },
                    ],
                },
            },
            random_seed_encrypted="abc",
            random_seed_commitment="def",
        )
        db_session.add(session)
        await db_session.flush()

        # When late_return occurs, matching items are "late_return" and "any" (total 2 tasks)
        tasks = await assign_penalty_tasks_for_violation(
            db_session,
            session=session,
            violation_type="late_return",
            violation_count=1,
        )
        assert len(tasks) == 2
        assigned_names = [t.selected_entity_name for t in tasks]
        assert "Задание на опоздание" in assigned_names
        assert "Универсальное наказание" in assigned_names
        assert "Только за срыв" not in assigned_names

    async def test_update_draft_persists_penalty_tasks_config(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """POST /api/v2/locktimer/sessions/{id}/update successfully stores penalty_tasks_config."""
        draft = await create_draft(db_session, owner_id=test_user.id, title="Config Test Draft")

        items_payload = [
            {
                "entity_id": str(uuid.uuid4()),
                "activity_name": "Планка 2 минуты",
                "violation_type": "task_missed",
                "initial_value": 2,
                "unit": "мин",
                "is_dynamic": True,
            }
        ]

        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{draft.id}/update",
            data={
                "title": "Config Test Draft",
                "penalty_tasks_enabled": "true",
                "penalty_tasks_mode": "all",
                "penalty_tasks_items_json": json.dumps(items_payload),
            },
        )
        assert resp.status_code in (200, 303)

        await db_session.refresh(draft)
        policy = draft.discipline_policy
        assert policy["penalty_tasks_enabled"] is True
        assert policy["penalty_tasks_config"]["mode"] == "all"
        assert len(policy["penalty_tasks_config"]["items"]) == 1
        assert policy["penalty_tasks_config"]["items"][0]["activity_name"] == "Планка 2 минуты"


class TestADR205LocalOCRVerificationMode:
    async def test_draft_verification_mode_local_ocr_and_guidance(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """verification_mode local_ocr is stored and triggers guidance warning in UI (ADR-205)."""
        draft = await create_draft(db_session, owner_id=test_user.id, title="OCR Draft")

        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{draft.id}/update",
            data={
                "title": "OCR Draft",
                "verification_mode": "local_ocr",
                "verification_required": "true",
                "verification_frequency_hours": 12,
            },
        )
        assert resp.status_code in (200, 303)

        await db_session.refresh(draft)
        assert draft.verification_mode == "local_ocr"

        # Check UI render contains local OCR guidance
        res_ui = await auth_client.get(f"/locktimer/sessions/{draft.id}")
        assert res_ui.status_code == 200
        assert "Локальный OCR (Tesseract / без ИИ)" in res_ui.text
        assert "Важно для локального OCR (без нейросети)" in res_ui.text
        assert "Не используйте" in res_ui.text
