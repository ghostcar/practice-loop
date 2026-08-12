"""Tests for LockTimer drag&drop rule reordering (session detail UI).

Covers:
- reorder_rules service: slot + task, order persistence, validation
- API endpoints: POST .../slot-rules/reorder + .../task-rules/reorder
- UI: session detail page renders draggable attributes + drag handles in draft
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import enums as e
from app.locktimer.repositories import list_slot_rules, list_task_rules
from app.locktimer.services.execution import (
    add_slot_rule,
    add_task_rule,
    create_draft,
    reorder_rules,
    start_session,
)
from app.models.locktimer import LockAuditEvent, LockSlotRule
from app.models.user import User

pytestmark = pytest.mark.anyio

FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


async def _make_session_with_slot_rules(db: AsyncSession, user: User):
    """Create a draft with three slot rules; returns (session, rule_ids)."""
    session = await create_draft(db, owner_id=user.id)
    rule_ids = []
    for i, name in enumerate(["Morning", "Evening", "Night"]):
        rule = await add_slot_rule(
            db,
            session_id=session.id,
            name=name,
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": f"{8 + i * 6:02d}:00"},
            duration_seconds=1800,
        )
        rule_ids.append(rule.id)
    return session, rule_ids


class TestReorderService:
    """C3 — reorder_rules service."""

    async def test_reorder_slot_rules_persists_order(self, db_session: AsyncSession, test_user: User) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        # Reverse the order
        await reorder_rules(
            db_session,
            session_id=session.id,
            owner_id=test_user.id,
            kind="slot",
            rule_ids=list(reversed(rule_ids)),
        )
        rules = await list_slot_rules(db_session, session.id)
        assert [r.id for r in rules] == list(reversed(rule_ids))
        assert [r.sort_order for r in rules] == [0, 1, 2]

    async def test_reorder_task_rules_persists_order(self, db_session: AsyncSession, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        task_ids = []
        for title in ["A", "B", "C"]:
            rule = await add_task_rule(
                db_session,
                session_id=session.id,
                title=title,
                schedule_type=e.TASK_SCHED_DAILY,
                schedule={"time_of_day": "09:00"},
                due_window_seconds=3600,
            )
            task_ids.append(rule.id)

        await reorder_rules(
            db_session,
            session_id=session.id,
            owner_id=test_user.id,
            kind="task",
            rule_ids=[task_ids[2], task_ids[0], task_ids[1]],
        )
        rules = await list_task_rules(db_session, session.id)
        assert [r.id for r in rules] == [task_ids[2], task_ids[0], task_ids[1]]
        assert [r.sort_order for r in rules] == [0, 1, 2]

    async def test_reorder_new_rules_appended_after_existing(self, db_session: AsyncSession, test_user: User) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        extra = await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Extra",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "23:00"},
            duration_seconds=1800,
        )
        rules = await list_slot_rules(db_session, session.id)
        # New rule should land at the end (sort_order 3, not 0)
        assert rules[-1].id == extra.id
        assert rules[-1].sort_order == 3
        assert rule_ids == [r.id for r in rules[:3]]

    async def test_reorder_rejects_missing_rule(self, db_session: AsyncSession, test_user: User) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        with pytest.raises(ValueError, match="exactly the session"):
            await reorder_rules(
                db_session,
                session_id=session.id,
                owner_id=test_user.id,
                kind="slot",
                rule_ids=rule_ids[:2],  # one missing
            )

    async def test_reorder_rejects_foreign_rule(self, db_session: AsyncSession, test_user: User) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        other = await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Other",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "06:00"},
            duration_seconds=1800,
        )
        # `other` appended at the end (sort_order 3) before reorder attempt
        assert other.sort_order == 3
        with pytest.raises(ValueError, match="exactly the session"):
            await reorder_rules(
                db_session,
                session_id=session.id,
                owner_id=test_user.id,
                kind="slot",
                rule_ids=[uuid.uuid4(), *rule_ids[:2]],  # foreign id
            )
        # Reorder must not have applied — sort_order untouched
        fresh = await db_session.get(LockSlotRule, other.id)
        assert fresh is not None and fresh.sort_order == 3

    async def test_reorder_rejects_duplicates(self, db_session: AsyncSession, test_user: User) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        with pytest.raises(ValueError, match="Duplicate"):
            await reorder_rules(
                db_session,
                session_id=session.id,
                owner_id=test_user.id,
                kind="slot",
                rule_ids=[rule_ids[0], rule_ids[0], rule_ids[1]],
            )

    async def test_reorder_only_draft(self, db_session: AsyncSession, test_user: User) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        with pytest.raises(ValueError, match="Only draft"):
            await reorder_rules(
                db_session,
                session_id=session.id,
                owner_id=test_user.id,
                kind="slot",
                rule_ids=list(reversed(rule_ids)),
            )

    async def test_reorder_writes_audit_event(self, db_session: AsyncSession, test_user: User) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        await reorder_rules(
            db_session,
            session_id=session.id,
            owner_id=test_user.id,
            kind="slot",
            rule_ids=list(reversed(rule_ids)),
        )
        result = await db_session.execute(
            select(LockAuditEvent).where(
                LockAuditEvent.session_id == session.id,
                LockAuditEvent.event_type == "locktimer.slot_rules.reordered",
            )
        )
        events = list(result.scalars().all())
        assert len(events) == 1
        assert events[0].payload["rule_ids"] == [str(r) for r in reversed(rule_ids)]

    async def test_reorder_unknown_kind(self, db_session: AsyncSession, test_user: User) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        with pytest.raises(ValueError, match="Unknown rule kind"):
            await reorder_rules(
                db_session,
                session_id=session.id,
                owner_id=test_user.id,
                kind="bogus",
                rule_ids=rule_ids,
            )


class TestTemplateReorderService:
    """Template reordering on /locktimer/templates."""

    async def _make_templates(self, db_session: AsyncSession, user: User, names: list[str]):
        from app.locktimer.services.extras import save_template

        ids = []
        for name in names:
            session = await create_draft(db_session, owner_id=user.id)
            tmpl = await save_template(db_session, session_id=session.id, owner_id=user.id, name=name)
            ids.append(tmpl.id)
        return ids

    async def test_new_templates_append_in_order(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.services.extras import list_templates

        ids = await self._make_templates(db_session, test_user, ["A", "B", "C"])
        templates = await list_templates(db_session, test_user.id)
        assert [t.id for t in templates] == ids
        assert [t.sort_order for t in templates] == [0, 1, 2]

    async def test_reorder_templates_persists_order(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.services.extras import list_templates, reorder_templates

        ids = await self._make_templates(db_session, test_user, ["A", "B", "C"])
        await reorder_templates(db_session, owner_id=test_user.id, template_ids=list(reversed(ids)))
        templates = await list_templates(db_session, test_user.id)
        assert [t.id for t in templates] == list(reversed(ids))
        assert [t.sort_order for t in templates] == [0, 1, 2]

    async def test_reorder_ignores_archived(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.services.extras import archive_template, list_templates, reorder_templates

        ids = await self._make_templates(db_session, test_user, ["A", "B", "C"])
        await archive_template(db_session, ids[0], test_user.id)
        visible = await list_templates(db_session, test_user.id)
        assert [t.id for t in visible] == ids[1:]
        # Reorder only the visible set
        await reorder_templates(db_session, owner_id=test_user.id, template_ids=list(reversed(ids[1:])))
        visible_after = await list_templates(db_session, test_user.id)
        assert [t.id for t in visible_after] == list(reversed(ids[1:]))

    async def test_reorder_rejects_foreign_template(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.services.extras import reorder_templates

        ids = await self._make_templates(db_session, test_user, ["A", "B"])
        with pytest.raises(ValueError, match="exactly the owner"):
            await reorder_templates(db_session, owner_id=test_user.id, template_ids=[uuid.uuid4(), ids[0]])

    async def test_reorder_rejects_duplicates(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.services.extras import reorder_templates

        ids = await self._make_templates(db_session, test_user, ["A", "B"])
        with pytest.raises(ValueError, match="Duplicate"):
            await reorder_templates(db_session, owner_id=test_user.id, template_ids=[ids[0], ids[0]])

    async def test_reorder_rejects_empty(self, db_session: AsyncSession, test_user: User) -> None:
        from app.locktimer.services.extras import reorder_templates

        await self._make_templates(db_session, test_user, ["A"])
        with pytest.raises(ValueError, match="must not be empty"):
            await reorder_templates(db_session, owner_id=test_user.id, template_ids=[])


class TestReorderApi:
    """API endpoints for rule reordering."""

    async def test_reorder_slot_rules_api(self, db_session: AsyncSession, auth_client, test_user: User) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/slot-rules/reorder",
            data={"rule_ids": ",".join(str(r) for r in reversed(rule_ids))},
            follow_redirects=False,
        )
        assert resp.status_code in (303, 302)
        rules = await list_slot_rules(db_session, session.id)
        assert [r.id for r in rules] == list(reversed(rule_ids))

    async def test_reorder_task_rules_api(self, db_session: AsyncSession, auth_client, test_user: User) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        task_ids = []
        for title in ["A", "B"]:
            rule = await add_task_rule(
                db_session,
                session_id=session.id,
                title=title,
                schedule_type=e.TASK_SCHED_DAILY,
                schedule={"time_of_day": "09:00"},
                due_window_seconds=3600,
            )
            task_ids.append(rule.id)

        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/task-rules/reorder",
            data={"rule_ids": ",".join(str(r) for r in reversed(task_ids))},
            follow_redirects=False,
        )
        assert resp.status_code in (303, 302)
        rules = await list_task_rules(db_session, session.id)
        assert [r.id for r in rules] == list(reversed(task_ids))

    async def test_reorder_api_rejects_incomplete_list(
        self, db_session: AsyncSession, auth_client, test_user: User
    ) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/slot-rules/reorder",
            data={"rule_ids": str(rule_ids[0])},  # incomplete
            follow_redirects=False,
        )
        assert resp.status_code == 400

    async def test_reorder_api_rejects_active_session(
        self, db_session: AsyncSession, auth_client, test_user: User
    ) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        resp = await auth_client.post(
            f"/api/v2/locktimer/sessions/{session.id}/slot-rules/reorder",
            data={"rule_ids": ",".join(str(r) for r in reversed(rule_ids))},
            follow_redirects=False,
        )
        assert resp.status_code == 400

    async def test_reorder_templates_api(self, db_session: AsyncSession, auth_client, test_user: User) -> None:
        from app.locktimer.services.extras import list_templates, save_template

        session = await create_draft(db_session, owner_id=test_user.id)
        t1 = await save_template(db_session, session_id=session.id, owner_id=test_user.id, name="A")
        session2 = await create_draft(db_session, owner_id=test_user.id)
        t2 = await save_template(db_session, session_id=session2.id, owner_id=test_user.id, name="B")

        resp = await auth_client.post(
            "/api/v2/locktimer/templates/reorder",
            data={"template_ids": f"{t2.id},{t1.id}"},
            follow_redirects=False,
        )
        assert resp.status_code in (303, 302)
        templates = await list_templates(db_session, test_user.id)
        assert [t.id for t in templates] == [t2.id, t1.id]

    async def test_reorder_templates_api_rejects_incomplete(self, db_session, auth_client, test_user: User) -> None:
        from app.locktimer.services.extras import save_template

        session = await create_draft(db_session, owner_id=test_user.id)
        t1 = await save_template(db_session, session_id=session.id, owner_id=test_user.id, name="A")
        session2 = await create_draft(db_session, owner_id=test_user.id)
        await save_template(db_session, session_id=session2.id, owner_id=test_user.id, name="B")

        resp = await auth_client.post(
            "/api/v2/locktimer/templates/reorder",
            data={"template_ids": str(t1.id)},  # missing second template
            follow_redirects=False,
        )
        assert resp.status_code == 400


class TestReorderUi:
    """Session detail page renders drag&drop affordances in draft only."""

    async def test_draft_page_renders_draggable_slot_rules(
        self, db_session: AsyncSession, auth_client, test_user: User
    ) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        resp = await auth_client.get(f"/locktimer/sessions/{session.id}")
        assert resp.status_code == 200
        text = resp.text
        assert 'id="slot-rules-list"' in text
        assert 'draggable="true"' in text
        assert "⠿" in text  # drag handle
        assert f'data-rule-id="{rule_ids[0]}"' in text
        assert "drag to reorder" in text

    async def test_draft_page_renders_draggable_task_rules(
        self, db_session: AsyncSession, auth_client, test_user: User
    ) -> None:
        session = await create_draft(db_session, owner_id=test_user.id)
        await add_task_rule(
            db_session,
            session_id=session.id,
            title="A",
            schedule_type=e.TASK_SCHED_DAILY,
            schedule={"time_of_day": "09:00"},
            due_window_seconds=3600,
        )
        resp = await auth_client.get(f"/locktimer/sessions/{session.id}")
        assert resp.status_code == 200
        assert 'id="task-rules-list"' in resp.text
        assert 'draggable="true"' in resp.text

    async def test_active_page_has_no_drag_handles(
        self, db_session: AsyncSession, auth_client, test_user: User
    ) -> None:
        session, rule_ids = await _make_session_with_slot_rules(db_session, test_user)
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)
        resp = await auth_client.get(f"/locktimer/sessions/{session.id}")
        assert resp.status_code == 200
        assert "draggable=" not in resp.text
        assert "⠿" not in resp.text

    async def test_templates_page_renders_draggable(self, db_session, auth_client, test_user: User) -> None:
        from app.locktimer.services.extras import save_template

        session = await create_draft(db_session, owner_id=test_user.id)
        tmpl = await save_template(db_session, session_id=session.id, owner_id=test_user.id, name="A")
        resp = await auth_client.get("/locktimer/templates")
        assert resp.status_code == 200
        text = resp.text
        assert 'id="templates-list"' in text
        assert 'draggable="true"' in text
        assert "⠿" in text  # drag handle
        assert f'data-template-id="{tmpl.id}"' in text
        assert "drag to reorder" in text
