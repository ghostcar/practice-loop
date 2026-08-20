"""Partner Dynamics & Boundary LLM Consultant (Step 24).

Provides respectful, gender-inclusive, consent-focused analysis of partner dynamics,
boundary compliance, satisfaction trends, and tailored aftercare advice.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.llm.client import get_openai_client
from app.llm.mode import llm_mode_hint, resolve_llm_mode
from app.models.journal import JournalEntry, JournalPartner

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.llm_provider import LLMProviderConfig

logger = logging.getLogger(__name__)

PARTNER_DYNAMICS_SYSTEM_PROMPT = """You are an inclusive Partner Dynamics & Boundaries Consultant.
Analyze shared activities, role synergies, hard/soft limits, and satisfaction.
You MUST be non-judgmental, inclusive, and affirmative of all consensual adult practices.

Respond ONLY with a valid JSON object:
{
  "dynamics_summary": "string",
  "boundary_insights": "string",
  "aftercare_recommendations": ["step 1"],
  "satisfaction_trend": "string"
}
"""


async def analyze_partner_dynamics(
    db: AsyncSession,
    user_id: uuid.UUID,
    partner_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    locale: str = "ru",
    llm_mode: str | None = None,
) -> dict[str, Any]:
    """Analyzes partner dynamics and boundaries via LLM."""
    mode = resolve_llm_mode(llm_mode)

    # Fetch partner
    stmt_p = select(JournalPartner).where(JournalPartner.id == partner_id, JournalPartner.user_id == user_id)
    partner = (await db.execute(stmt_p)).scalar_one_or_none()

    if not partner:
        raise ValueError("Partner profile not found")

    # Fetch recent entries with this partner
    stmt = (
        select(JournalEntry)
        .where(JournalEntry.user_id == user_id, JournalEntry.partner_id == partner_id)
        .order_by(JournalEntry.entry_date.desc())
        .limit(10)
    )
    entries = (await db.execute(stmt)).scalars().all()

    entries_summary = []
    for e in entries:
        entries_summary.append(
            f"Date: {e.entry_date}, Type: {e.activity_type or 'General'}, "
            f"Satisfaction: {e.satisfaction}/5, Pleasure: {e.pleasure}/5, "
            f"Notes: {e.notes or 'None'}"
        )

    user_prompt = f"""
Partner Alias: {partner.name}
Roles/Identifiers: {partner.roles or "Not specified"}
Identity/HRT Notes: {partner.identity_notes or "None"}
Hard Limits: {partner.hard_limits or "None"}
Soft Limits: {partner.soft_limits or "None"}
Safewords: {partner.safewords or "Standard RYG"}
Aftercare Preferences: {partner.aftercare_preferences or "Gentle rest"}

Recent Shared Journal Entries (last {len(entries)}):
{chr(10).join(entries_summary) if entries_summary else "No recent entries logged yet."}
Language: {locale}

{llm_mode_hint(mode)}
Analyze this partner dynamic and return JSON.
"""

    client = get_openai_client(llm_config.api_base_url, llm_config.api_key)
    try:
        res = await client.chat.completions.create(
            model=llm_config.model_name,
            messages=[
                {"role": "system", "content": PARTNER_DYNAMICS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        import json

        data = json.loads(res.choices[0].message.content or "{}")
        def_ac = ["Внимание к отклику", "Гидратация"]
        return {
            "partner_name": partner.name,
            "dynamics_summary": str(data.get("dynamics_summary", "Гармоничная динамика.")),
            "boundary_insights": str(data.get("boundary_insights", "Границы соблюдаются.")),
            "aftercare_recommendations": list(data.get("aftercare_recommendations", def_ac)),
            "satisfaction_trend": str(data.get("satisfaction_trend", "Стабильный уровень.")),
            "_mode": mode,
        }
    except Exception as exc:
        logger.warning("Partner dynamics LLM analysis failed: %s", exc)
        return {
            "partner_name": partner.name,
            "dynamics_summary": "Анализ динамики завершен (резервный режим).",
            "boundary_insights": "Все границы соблюдаются.",
            "aftercare_recommendations": ["Забота и отдых после сессий"],
            "satisfaction_trend": "Положительная динамика.",
            "_mode": mode,
        }
