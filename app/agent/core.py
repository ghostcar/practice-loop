"""Core Agent Loop Engine for PracticeLoop Agent (Step 44 / ADR-123)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.persona import build_persona_system_prompt
from app.agent.tools import AGENT_TOOLS_SCHEMA, execute_agent_tool
from app.llm.client import call_llm
from app.llm.pipeline import get_active_llm_config

logger = logging.getLogger(__name__)


async def run_practice_agent(
    user_prompt: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    persona_role: str = "keyholder",
) -> dict[str, Any]:
    """Runs single-turn or multi-turn agent tool execution loop."""
    llm_config = await get_active_llm_config(db, user_id)
    if not llm_config:
        return {
            "status": "error",
            "reply": "LLM-конфигурация не найдена. Пожалуйста, укажите BYOK-ключ в настройках.",
            "tool_calls": [],
        }

    system_prompt = build_persona_system_prompt(persona_role)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    executed_tools = []

    try:
        # Call LLM with tools enabled
        llm_res = await call_llm(
            config=llm_config,
            messages=messages,
            tools=AGENT_TOOLS_SCHEMA,
            tool_choice="auto",
        )

        content = llm_res.get("content", "")
        tool_calls = llm_res.get("tool_calls", [])

        # If LLM requested tool calls, execute them
        if tool_calls:
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name")
                raw_args = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                tool_res = await execute_agent_tool(
                    tool_name=fn_name,
                    arguments=args,
                    user_id=user_id,
                    db=db,
                )
                executed_tools.append({"tool": fn_name, "args": args, "result": tool_res})

                # Append tool response to messages
                messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                messages.append({"role": "tool", "tool_call_id": tc.get("id", "tc_0"), "content": json.dumps(tool_res)})

            # Second turn to get final natural language synthesis
            final_res = await call_llm(config=llm_config, messages=messages)
            content = final_res.get("content", "Задание или операция обработана.")

        return {
            "status": "success",
            "reply": content or "Запрос успешно обработан ИИ-Ассистентом.",
            "tool_calls": executed_tools,
        }

    except Exception as exc:
        logger.error(f"Agent execution error: {exc}", exc_info=True)
        return {
            "status": "error",
            "reply": f"Ошибка исполнения Агента: {exc}",
            "tool_calls": executed_tools,
        }
