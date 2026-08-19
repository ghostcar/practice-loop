"""Aftercare & Personal Care LLM Pipeline (Step 23).

Generates personalized Aftercare recovery guidance, recommended care products, and pharma ERP intake
suggestions based on user health recovery metrics, skin sensitivity, and post-session drop.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.llm.client import get_openai_client
from app.llm.mode import llm_mode_hint, resolve_llm_mode
from app.models.care import CareProduct, CareRoutine
from app.models.health import HealthState
from app.models.medication import Medication
from app.timeutils import local_today

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.llm_provider import LLMProviderConfig

logger = logging.getLogger(__name__)

AFTERCARE_SYSTEM_PROMPT = """You are a compassionate, expert Aftercare & Recovery Assistant in PracticeLoop.
Your job is to analyze post-session condition, recovery level, and skin sensitivity
to provide a gentle, step-by-step Aftercare Protocol.

Respond ONLY with a valid JSON object:
{
  "protocol_title": "string",
  "immediate_actions": ["step 1"],
  "recommended_care_products": ["product 1"],
  "pharma_notes": "string",
  "recovery_message": "string"
}
"""


async def generate_aftercare_guidance(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    locale: str = "ru",
    llm_mode: str | None = None,
) -> dict[str, Any]:
    """Generates an LLM Aftercare Guidance protocol."""
    mode = resolve_llm_mode(llm_mode)
    today = local_today()

    # Health context
    health = (
        await db.execute(select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == today))
    ).scalar_one_or_none()

    # Products & Routines context
    products = (await db.execute(select(CareProduct).where(CareProduct.user_id == user_id))).scalars().all()
    prod_names = [f"{p.name} ({p.category})" for p in products]

    meds = (await db.execute(select(Medication).where(Medication.user_id == user_id))).scalars().all()
    med_names = [f"{m.name} ({m.active_ingredient or ''})" for m in meds]

    stmt = select(CareRoutine).where(CareRoutine.user_id == user_id, CareRoutine.aftercare_trigger_drop.is_(True))
    routines = (await db.execute(stmt)).scalars().all()

    drop_str = "YES (Active Post-Session Drop)" if (health and health.post_session_drop) else "None"
    rec_str = f"{health.recovery}/5" if (health and health.recovery) else "N/A"
    skin_str = f"{health.skin_sensitivity}/5" if (health and health.skin_sensitivity) else "N/A"

    user_prompt = f"""
Current Health State:
- Post-Session Drop: {drop_str}
- Recovery Level: {rec_str}
- Skin Sensitivity: {skin_str}
- Symptoms: {health.symptoms if health else 'None'}

Available Care Products: {", ".join(prod_names) if prod_names else "Basic hydration"}
Available Medications: {", ".join(med_names) if med_names else "None"}
Configured Aftercare Routines: {", ".join([r.name for r in routines]) if routines else "Default rest"}
Language: {locale}

{llm_mode_hint(mode)}
Generate a custom Aftercare protocol in JSON.
"""

    client = get_openai_client(llm_config.api_base_url, llm_config.api_key)
    try:
        res = await client.chat.completions.create(
            model=llm_config.model_name,
            messages=[
                {"role": "system", "content": AFTERCARE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        import json

        data = json.loads(res.choices[0].message.content or "{}")
        return {
            "protocol_title": str(data.get("protocol_title", "Протокол Восстановления (Aftercare)")),
            "immediate_actions": list(data.get("immediate_actions", ["Пить воду", "Отдых"])),
            "recommended_care_products": list(data.get("recommended_care_products", [])),
            "pharma_notes": str(data.get("pharma_notes", "")),
            "recovery_message": str(data.get("recovery_message", "Позаботьтесь о себе после сессии.")),
            "_mode": mode,
        }
    except Exception as exc:
        logger.warning("Aftercare LLM generation failed: %s", exc)
        return {
            "protocol_title": "Протокол Восстановления (Aftercare)",
            "immediate_actions": ["Отдых и гидратация", "Теплый душ/ванна"],
            "recommended_care_products": [],
            "pharma_notes": "",
            "recovery_message": "Отдохните и восполните ресурс.",
            "_mode": mode,
        }
