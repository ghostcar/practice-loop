"""ADR-191 regression: agent call sites use the real call_llm signature.

The agent previously called ``call_llm(..., messages=..., tool_choice=...)`` —
a signature that never existed — which raised TypeError on every agent run.
``call_llm`` now accepts an optional full ``messages`` list (multi-turn), and
the agent passes system_prompt/user_message for the first turn.
"""

import pytest


async def _make_llm_config(db_session, test_user) -> None:
    from app.models.llm_config import LLMProviderConfig

    db_session.add(
        LLMProviderConfig(
            user_id=test_user.id,
            provider_name="test",
            api_base_url="http://localhost/v1",
            model_name="test-model",
            is_active=True,
        )
    )
    await db_session.flush()


def _fake_provider(captured: dict | None = None, error: Exception | None = None):
    """Fake AsyncOpenAI stand-in: records kwargs, raises error if requested."""

    class FakeCompletions:
        async def create(self, **kwargs):
            if error is not None:
                raise error
            if captured is not None:
                captured["messages"] = kwargs["messages"]
                captured["kwargs"] = kwargs

            class _Usage:
                prompt_tokens = 5
                completion_tokens = 7
                total_tokens = 12

            class _Message:
                content = '{"ok": true}'
                tool_calls = None

            class _Choice:
                message = _Message()

            class _Resp:
                usage = _Usage()
                choices = [_Choice()]

            return _Resp()

    class FakeClient:
        def __init__(self, *a, **kw):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

        async def close(self):
            pass

    return FakeClient


@pytest.mark.asyncio
async def test_call_llm_messages_param_wins(db_session, test_user, monkeypatch):
    """messages= is passed to the provider as-is (multi-turn), not rebuilt."""
    from app.llm import client as llm_client

    captured = {}
    monkeypatch.setattr(llm_client, "AsyncOpenAI", _fake_provider(captured=captured))
    await _make_llm_config(db_session, test_user)

    from app.llm.pipeline import get_active_llm_config

    cfg = await get_active_llm_config(db_session, test_user.id)
    assert cfg is not None

    tool_call = {"id": "tc_0", "type": "function", "function": {"name": "x", "arguments": "{}"}}
    multi = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": None, "tool_calls": [tool_call]},
        {"role": "tool", "tool_call_id": "tc_0", "content": "{}"},
    ]
    res = await llm_client.call_llm(cfg, messages=multi, db=db_session, user_id=test_user.id)
    assert captured["messages"] == multi
    assert res["content"] == '{"ok": true}'

    # log written
    from sqlalchemy import select

    from app.models.llm_config import LLMCallLog

    rows = (await db_session.execute(select(LLMCallLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "ok"
    assert rows[0].section is None  # no set_call_meta — falls back to None


@pytest.mark.asyncio
async def test_call_llm_requires_conversation(db_session, test_user):
    """Neither messages nor system_prompt+user_message → clear error."""
    from app.llm import client as llm_client

    await _make_llm_config(db_session, test_user)
    from app.llm.pipeline import get_active_llm_config

    cfg = await get_active_llm_config(db_session, test_user.id)
    with pytest.raises(ValueError, match="call_llm: pass system_prompt\\+user_message or messages"):
        await llm_client.call_llm(cfg, db=db_session, user_id=test_user.id)


@pytest.mark.asyncio
async def test_run_practice_agent_first_turn_signature(db_session, test_user, monkeypatch):
    """agent first turn calls call_llm with system_prompt/user_message (regression)."""

    await _make_llm_config(db_session, test_user)

    calls = []

    async def fake_call_llm(**kwargs):
        calls.append(kwargs)
        return {"content": "готово", "tool_calls": [], "usage": {"total_tokens": 1}}

    monkeypatch.setattr("app.agent.core.call_llm", fake_call_llm)
    # avoid prompt-library DB work in tests
    monkeypatch.setattr("app.agent.core.fetch_persona_system_prompt", _fake_fetch_persona)
    monkeypatch.setattr("app.agent.core.recall_user_memories", _fake_recall)

    from app.agent.core import run_practice_agent

    out = await run_practice_agent("привет", test_user.id, db_session)
    assert out["status"] == "success"
    assert calls, "call_llm должен быть вызван"
    first = calls[0]
    assert "messages" not in first
    assert first["system_prompt"]
    assert first["user_message"] == "привет"
    assert first["db"] is db_session
    assert first["user_id"] == test_user.id


async def _fake_fetch_persona(*args, **kwargs):
    return "system persona"


async def _fake_recall(*args, **kwargs):
    return []
