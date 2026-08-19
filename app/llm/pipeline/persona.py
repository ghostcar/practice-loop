"""Unified LLM Persona Engine (AI Keyholder / Top / Master / Observer — Step 26).

Provides centralized configuration for the AI Agent persona, strictness levels, tone,
and 1-Click medical/personal report exporter.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.health import HealthState
from app.models.journal import JournalEntry, JournalPartner
from app.models.locktimer import LockSession
from app.timeutils import local_today

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def build_unified_persona_prompt(
    persona_role: str = "keyholder",
    strictness: int = 3,
    tone: str = "authoritative",
    locale: str = "ru",
) -> str:
    """Builds the unified system prompt header for LLM Keyholder / Top / Master."""
    role_titles = {
        "observer": "AI Companion & Observer",
        "keyholder": "AI Keyholder & Controller",
        "top": "AI Top / Master & Instructor",
    }
    title = role_titles.get(persona_role, "AI Keyholder & Master")

    return f"""You are acting in the role of: {title}.
Persona Settings:
- Strictness: {strictness}/5
- Tone: {tone}
- Language: {locale}

Core Directive: Guide the user with absolute respect for boundaries, consent, and safety.
"""


async def generate_personal_medical_report(
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int = 30,
) -> dict[str, Any]:
    """Generates a structured 1-Click Medical / Personal report for export."""
    today = local_today()

    # Health states
    h_states = (
        (
            await db.execute(
                select(HealthState)
                .where(HealthState.user_id == user_id)
                .order_by(HealthState.event_date.desc())
                .limit(days)
            )
        )
        .scalars()
        .all()
    )

    # Locks
    locks = (
        (await db.execute(select(LockSession).where(LockSession.owner_id == user_id))).scalars().all()
    )

    # Partners
    partners = (
        (await db.execute(select(JournalPartner).where(JournalPartner.user_id == user_id))).scalars().all()
    )

    # Entries
    entries = (
        (await db.execute(select(JournalEntry).where(JournalEntry.user_id == user_id))).scalars().all()
    )

    report_md = f"""# 📊 PracticeLoop Personal & Health Report
*Generated on: {today.isoformat()}*

## 1. Health & HRT Summary (Last {len(h_states)} logs)
- Total Health Logs: {len(h_states)}
- Post-Session Drop Events: {sum(1 for h in h_states if h.post_session_drop)}
- HRT Intake Logged: {sum(1 for h in h_states if h.hrt_taken)}

## 2. Chastity & Lock Dynamics
- Active/Historical Locks: {len(locks)}

## 3. Partners & Boundaries
- Registered Partner Aliases: {len(partners)}
- Total Journal Entries: {len(entries)}
"""

    return {
        "report_markdown": report_md,
        "health_logs_count": len(h_states),
        "locks_count": len(locks),
        "generated_at": today.isoformat(),
    }
