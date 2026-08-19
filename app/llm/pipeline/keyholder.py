"""Chastity AI Keyholder Pipeline (Chaster.app paradigm — Step 21).

Provides LLM AI Keyholder decision engine for lock extensions, tag verification reviews,
emergency unlocks, and daily check-ins.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.llm.client import get_openai_client
from app.llm.mode import llm_mode_hint, resolve_llm_mode
from app.models.health import HealthState
from app.models.locktimer import LockSession
from app.timeutils import local_today

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.llm_provider import LLMProviderConfig

logger = logging.getLogger(__name__)


KEYHOLDER_SYSTEM_PROMPT = """You are an AI Keyholder Bot overseeing a Chastity Lock session in the Chaster.app paradigm.
Your role is to evaluate user requests with care, consistency, and authority.

Core Principles:
1. Safety First: If health state indicates cramps, recovery <= 2, or Drop, grant a relief pause or emergency release.
2. Discipline: Evaluate completed tasks, tag verifications, and streak adherence.
3. Tone: Respectful, firm, authoritative yet protective (D/s Keyholder dynamics).

Respond ONLY with a valid JSON object:
{
  "decision": "approve" | "deny" | "grant_extension" | "emergency_granted" | "relief_hold",
  "added_duration_minutes": integer,
  "keyholder_message": "string"
}
"""


async def evaluate_keyholder_action(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    action_kind: str,
    reason: str,
    llm_config: LLMProviderConfig,
    locale: str = "ru",
    llm_mode: str | None = None,
) -> dict[str, Any]:
    """Evaluates a Chastity Lock action using the AI Keyholder LLM Bot."""
    mode = resolve_llm_mode(llm_mode)
    today = local_today()

    # Gather HealthState context
    health_state = (
        await db.execute(select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == today))
    ).scalar_one_or_none()

    # Gather LockSession context
    lock_sess = (
        await db.execute(select(LockSession).where(LockSession.id == session_id, LockSession.owner_id == user_id))
    ).scalar_one_or_none()

    health_info = "Normal"
    if health_state:
        drop = "ACTIVE (Post-session Drop)" if health_state.post_session_drop else "None"
        rec = f"{health_state.recovery}/5" if health_state.recovery else "N/A"
        health_info = f"Drop: {drop}, Recovery: {rec}, Symptoms: {health_state.symptoms or 'None'}"

    user_prompt = f"""
Action Requested: {action_kind}
User Reason / Note: {reason or 'No note provided'}
Lock State: {lock_sess.state if lock_sess else 'active'}
Current User Health Context: {health_info}
Language: {locale}

{llm_mode_hint(mode)}
Evaluate this request and output JSON according to the schema.
"""

    client = get_openai_client(llm_config.api_base_url, llm_config.api_key)
    try:
        res = await client.chat.completions.create(
            model=llm_config.model_name,
            messages=[
                {"role": "system", "content": KEYHOLDER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        raw_content = res.choices[0].message.content or "{}"
        import json

        data = json.loads(raw_content)
        return {
            "decision": str(data.get("decision", "approve")),
            "added_duration_minutes": int(data.get("added_duration_minutes", 0)),
            "keyholder_message": str(data.get("keyholder_message", "Запрос обработан Ключником.")),
            "_mode": mode,
        }
    except Exception as exc:
        logger.warning("AI Keyholder LLM failed: %s", exc)
        return {
            "decision": "approve",
            "added_duration_minutes": 0,
            "keyholder_message": "Ключник подтвердил запрос (резервный режим).",
            "_mode": mode,
        }
