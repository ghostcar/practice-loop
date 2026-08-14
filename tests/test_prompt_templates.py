"""Tests for Step 6 — LLM tools: prompt library, templates, private KB.

Covers:
1. Prompt library — registry completeness, rendering, i18n keys present.
2. Template engine — variable extraction/rendering, params validation,
   text and task generation paths (with mocked LLM client).
3. Prompt templates API — CRUD, from-library creation, generation endpoint.
4. Private knowledge base — document collection, lexical fallback,
   context formatting, availability gate.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.en import EN
from app.i18n.ru import RU
from app.llm.pipeline.templates import (
    extract_template_vars,
    generate_from_template,
    render_template_prompt,
)
from app.llm.prompt_library import get_prompt, list_prompts, prompt_categories, render_system_prompt
from app.models.prompt_template import PromptTemplate
from app.models.user import User

pytestmark = pytest.mark.anyio


# ── Prompt library ───────────────────────────────────────────────────────────


class TestPromptLibrary:
    def test_registry_has_core_prompts(self):
        keys = {p.key for p in list_prompts()}
        assert {"task.single", "task.weekly", "training.plan_day", "diet.generate"} <= keys

    def test_categories(self):
        cats = prompt_categories()
        assert "task" in cats and "training" in cats and "diet" in cats

    def test_lookup_and_render(self):
        p = get_prompt("task.single")
        assert p is not None
        rendered = render_system_prompt(p, locale="ru")
        assert "ru" in rendered or "JSON" in rendered

    def test_render_missing_locale_keeps_placeholder(self):
        p = get_prompt("training.plan_day")
        assert p is not None
        # Without locale the {locale} placeholder stays — no crash.
        rendered = render_system_prompt(p)
        assert "locale" in rendered

    def test_i18n_keys_exist_in_both_locales(self):
        for p in list_prompts():
            assert p.title_key in EN, f"{p.title_key} missing in EN"
            assert p.title_key in RU, f"{p.title_key} missing in RU"
            assert p.description_key in EN, f"{p.description_key} missing in EN"
            assert p.description_key in RU, f"{p.description_key} missing in RU"


# ── Template engine (pure functions) ─────────────────────────────────────────


class TestTemplateEngine:
    def test_extract_vars(self):
        assert extract_template_vars("Do {{intensity}} with {{count}} items") == ["intensity", "count"]
        assert extract_template_vars("No vars here") == []

    def test_render_substitutes(self):
        out = render_template_prompt("Do {{intensity}} x{{count}}", {"intensity": "hard", "count": 3})
        assert out == "Do hard x3"

    def test_render_missing_var_becomes_empty(self):
        out = render_template_prompt("a{{x}}b{{y}}c", {"x": "1"})
        assert out == "a1bc"

    def test_render_nested_value_json(self):
        out = render_template_prompt("data {{items}}", {"items": {"a": 1}})
        assert json.loads(out.split("data ")[1]) == {"a": 1}

    async def test_generate_text_with_mock(self, db_session: AsyncSession, test_user: User, monkeypatch):
        """Text template: mock call_llm, assert content returned."""
        from app.llm import client

        async def fake_call_llm(config, system_prompt, user_message, tools=None, json_mode=True):
            return {
                "content": "Generated text answer",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.001},
                "tool_calls": [],
            }

        monkeypatch.setattr(client, "call_llm", fake_call_llm)

        from app.models.llm_config import LLMProviderConfig

        cfg = LLMProviderConfig(
            user_id=test_user.id,
            provider_name="test",
            api_base_url="http://x/v1",
            model_name="m",
            is_active=True,
        )
        db_session.add(cfg)
        await db_session.flush()

        template = PromptTemplate(
            user_id=test_user.id,
            name="Coach",
            template_type="text",
            system_prompt="You are a coach. Use {{intensity}}.",
            params_schema=[{"key": "intensity", "type": "enum", "options": ["low", "high"], "required": True}],
        )
        db_session.add(template)
        await db_session.flush()

        result = await generate_from_template(
            db=db_session,
            user_id=test_user.id,
            llm_config=cfg,
            template=template,
            params={"intensity": "low"},
            locale="en",
        )
        assert result["type"] == "text"
        assert result["content"] == "Generated text answer"
        assert result["usage"]["total_tokens"] == 15

    async def test_generate_text_rejects_bad_params(self, db_session: AsyncSession, test_user: User):
        from app.models.llm_config import LLMProviderConfig

        cfg = LLMProviderConfig(
            user_id=test_user.id, provider_name="t", api_base_url="http://x", model_name="m", is_active=True
        )
        db_session.add(cfg)
        await db_session.flush()
        template = PromptTemplate(
            user_id=test_user.id,
            name="Strict",
            template_type="text",
            system_prompt="Use {{intensity}}",
            params_schema=[{"key": "intensity", "type": "enum", "options": ["a", "b"], "required": True}],
        )
        db_session.add(template)
        await db_session.flush()

        with pytest.raises(ValueError, match="Template params invalid"):
            await generate_from_template(
                db=db_session,
                user_id=test_user.id,
                llm_config=cfg,
                template=template,
                params={"intensity": "nope"},
                locale="en",
            )

    async def test_generate_task_with_mock(self, db_session: AsyncSession, test_user: User, monkeypatch):
        """Task template: mock LLM + allowed entity, assert ActivityLog created."""
        from app.llm import client, context_builder

        entity_id = uuid.uuid4()

        async def fake_build_context(db, user_id, session_id=None, locale="en"):
            return {
                "allowed_entities": [
                    {
                        "id": str(entity_id),
                        "name": "Test Activity",
                        "type": "test",
                        "category": "test",
                        "tags": [],
                        "intensity": "active",
                        "params_schema": [
                            {"key": "intensity", "type": "enum", "options": ["1", "2"], "required": False}
                        ],
                        "task_template": None,
                        "desire_level": "want",
                        "rating": 4,
                        "risk_level": "low",
                    }
                ],
                "recent_history": [],
                "stats": {"total_activities": 0, "completed": 0, "stopped": 0, "week_activities": 0},
                "active_penalties": [],
                "calendar_schedule": None,
                "active_diets": [],
                "today_training": None,
                "kb_context": None,
                "locale": locale,
            }

        async def fake_call_llm(config, system_prompt, user_message, tools=None, json_mode=True):
            payload = {
                "entity_id": str(entity_id),
                "entity_name": "Test Activity",
                "params": {"intensity": "2"},
                "reasoning": "chosen",
            }
            return {
                "content": json.dumps(payload),
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25, "cost": 0.002},
                "tool_calls": [],
            }

        monkeypatch.setattr(context_builder, "build_context", fake_build_context)
        monkeypatch.setattr(client, "call_llm", fake_call_llm)

        from app.models.llm_config import LLMProviderConfig

        cfg = LLMProviderConfig(
            user_id=test_user.id, provider_name="t", api_base_url="http://x", model_name="m", is_active=True
        )
        db_session.add(cfg)
        await db_session.flush()

        template = PromptTemplate(
            user_id=test_user.id,
            name="Task picker",
            template_type="task",
            system_prompt="Pick one activity from the list.",
        )
        db_session.add(template)
        await db_session.flush()

        result = await generate_from_template(
            db=db_session,
            user_id=test_user.id,
            llm_config=cfg,
            template=template,
            locale="en",
        )
        assert result["type"] == "task"
        assert result["entity_id"] == str(entity_id)

        # ActivityLog persisted
        from app.models.activity_log import ActivityLog

        saved = await db_session.execute(
            select(ActivityLog).where(ActivityLog.user_id == test_user.id, ActivityLog.entity_id == entity_id)
        )
        log = saved.scalar_one_or_none()
        assert log is not None
        assert log.status == "planned"
        assert log.selected_params == {"intensity": "2"}


# ── Prompt templates API ─────────────────────────────────────────────────────


class TestPromptTemplatesApi:
    async def test_library_page(self, auth_client):
        response = await auth_client.get("/llm/prompts")
        assert response.status_code == 200
        assert "task.single" in response.text or "Prompt Library" in response.text

    async def test_templates_page(self, auth_client):
        response = await auth_client.get("/llm/templates")
        assert response.status_code == 200

    async def test_create_template(self, auth_client):
        response = await auth_client.post(
            "/llm/templates",
            data={
                "name": "My Coach",
                "description": "Personal coach",
                "template_type": "text",
                "system_prompt": "You are my coach. Use {{intensity}}.",
                "params_schema": json.dumps(
                    [{"key": "intensity", "type": "enum", "options": ["low", "high"], "required": False}]
                ),
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        detail = await auth_client.get(response.headers["location"])
        assert detail.status_code == 200
        assert "My Coach" in detail.text

    async def test_create_template_invalid_schema(self, auth_client):
        response = await auth_client.post(
            "/llm/templates",
            data={
                "name": "Bad",
                "template_type": "text",
                "system_prompt": "x",
                "params_schema": json.dumps([{"key": "k", "type": "unknown_type"}]),
            },
        )
        assert response.status_code == 400

    async def test_create_from_library(self, auth_client):
        response = await auth_client.post(
            "/llm/templates/new-from-library",
            data={"key": "diet.generate", "name": "My Diet Plan", "template_type": "text"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        detail = await auth_client.get(response.headers["location"])
        assert detail.status_code == 200
        assert "My Diet Plan" in detail.text

    async def test_json_list(self, auth_client, test_user: User, db_session: AsyncSession):
        db_session.add(
            PromptTemplate(
                user_id=test_user.id,
                name="J1",
                template_type="text",
                system_prompt="x",
            )
        )
        await db_session.flush()
        response = await auth_client.get("/api/v2/prompt-templates")
        assert response.status_code == 200
        body = response.json()
        assert any(t["name"] == "J1" for t in body)

    async def test_json_generate_no_config(self, auth_client, test_user: User, db_session: AsyncSession):
        db_session.add(
            PromptTemplate(
                user_id=test_user.id,
                name="NoCfg",
                template_type="text",
                system_prompt="x",
            )
        )
        await db_session.flush()
        # No active LLM config for this user → 409
        response = await auth_client.post(f"/api/v2/prompt-templates/{uuid.uuid4()}/generate", json={"params": {}})
        assert response.status_code == 404


# ── Private knowledge base ───────────────────────────────────────────────────


class TestKnowledgeBase:
    async def test_collect_documents(self, db_session: AsyncSession, test_user: User):
        from app.models.activity_log import ActivityLog

        db_session.add(
            ActivityLog(
                user_id=test_user.id,
                status="planned",
                selected_entity_name="Rope Play",
                selected_params={"intensity": "2"},
            )
        )
        await db_session.flush()

        from app.knowledge.index import collect_user_documents

        docs = await collect_user_documents(db_session, test_user.id)
        assert any("Rope Play" in d["text"] for d in docs)
        assert all(d["user_id"] == str(test_user.id) for d in docs)

    async def test_lexical_ranking(self):
        from app.knowledge.retrieve import _lexical_ranking

        texts = [("rope play with intensity 2", "a"), ("unrelated note", "b"), ("rope and chains", "c")]
        ranked = _lexical_ranking(texts, "rope")
        assert ranked[0][1] == "a"
        assert "unrelated" not in [r[1] for r in ranked]

    async def test_format_kb_context(self):
        from app.knowledge.service import format_kb_context

        out = format_kb_context([{"text": "rope play", "source": "activity_log:x"}])
        assert out is not None
        assert "rope play" in out and "activity_log:x" in out
        assert format_kb_context([]) is None

    async def test_retrieve_lexical_fallback(self, db_session: AsyncSession, test_user: User, monkeypatch):
        """Without Qdrant backend → lexical fallback over own docs."""
        from app.knowledge import retrieve as kb_retrieve

        monkeypatch.setattr(kb_retrieve, "kb_backend_available", lambda: (False, "no deps"))

        from app.models.activity_log import ActivityLog

        db_session.add(ActivityLog(user_id=test_user.id, status="planned", selected_entity_name="Chastity Belt"))
        await db_session.flush()

        from app.knowledge.service import retrieve_relevant

        results = await retrieve_relevant(db_session, test_user.id, "chastity", limit=5)
        assert any("Chastity" in r["text"] for r in results)

    async def test_kb_api_degraded(self, auth_client, monkeypatch):
        # knowledge.py импортирует kb_backend_available на уровне модуля.
        import app.api.knowledge as kb_api

        monkeypatch.setattr(kb_api, "kb_backend_available", lambda: (False, "no deps"))
        response = await auth_client.get("/api/v2/knowledge/status")
        assert response.status_code == 200
        assert response.json()["available"] is False

        response = await auth_client.get("/api/v2/knowledge/search", params={"q": "rope"})
        assert response.status_code == 200
        assert response.json()["results"] == []
