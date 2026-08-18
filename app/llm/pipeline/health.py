"""LLM health pipeline — lab analysis (Step 13, ADR-087).

Driven by the user preference ``prefs.llm_mode`` (safe | expanded):

- safe: factual restatement + questions for a doctor, no recommendations;
- expanded: may also give recommendations/advice, including around medication.

Usage is tracked on the active LLMProviderConfig (tokens + cost), matching the
other LLM pipelines. The analysis is never persisted to a table — it is a
stateless on-demand interpretation shown on the /health page (raw response is
not stored; only usage counters are).
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import client
from app.llm.health_prompts import HEALTH_ANALYZE_SYSTEM_EXPANDED, HEALTH_ANALYZE_SYSTEM_SAFE
from app.llm.repair import parse_llm_json
from app.models.health import LabRecord
from app.models.llm_config import LLMProviderConfig
from app.models.medication import MedSchedule
from app.timeutils import local_today

logger = logging.getLogger(__name__)

ANALYSIS_DAYS = 180


async def analyze_labs(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    locale: str = "en",
    llm_mode: str = "safe",
) -> dict:
    """Analyze the user's recent lab records via LLM.

    Returns the parsed JSON dict with keys: summary, observations, assumptions,
    questions_for_doctor (+ recommendations in expanded mode). Tracks usage on
    ``llm_config``.
    """
    start = local_today() - timedelta(days=ANALYSIS_DAYS)
    labs = (
        (
            await db.execute(
                select(LabRecord)
                .where(LabRecord.user_id == user_id, LabRecord.measured_at >= start)
                .order_by(LabRecord.measured_at.desc())
            )
        )
        .scalars()
        .all()
    )
    if not labs:
        return {"summary": "", "observations": [], "assumptions": [], "questions_for_doctor": [], "recommendations": []}

    # Active medication schedules — context for expanded-mode advice around a
    # dosing scheme (and ignored in safe mode).
    schedules = (
        (
            await db.execute(
                select(MedSchedule)
                .where(MedSchedule.user_id == user_id, MedSchedule.is_active.is_(True))
                .order_by(MedSchedule.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    def _fmt_lab(rec: LabRecord) -> str:
        ref = ""
        if rec.ref_min is not None and rec.ref_max is not None:
            ref = f" (ref {rec.ref_min:g}–{rec.ref_max:g}{f' {rec.unit}' if rec.unit else ''})"
        elif rec.ref_min is not None:
            ref = f" (ref ≥{rec.ref_min:g}{f' {rec.unit}' if rec.unit else ''})"
        elif rec.ref_max is not None:
            ref = f" (ref ≤{rec.ref_max:g}{f' {rec.unit}' if rec.unit else ''})"
        flag = " [FLAGGED by lab]" if rec.flagged else ""
        return f"- {rec.measured_at}: {rec.name} = {rec.value:g}{f' {rec.unit}' if rec.unit else ''}{ref}{flag}"

    labs_text = "\n".join(_fmt_lab(rec) for rec in labs) or "- (no lab records)"
    sched_text = (
        "\n".join(
            f"- {s.medication.name if s.medication else '?'}: {s.dose_quantity:g} {s.dose_unit or ''}"
            f" ({s.frequency_type}{f' ×{s.times_per_day}' if s.times_per_day else ''})"
            for s in schedules
        )
        or "- (no active medication schedules)"
    )

    if llm_mode == "expanded":
        system_prompt = HEALTH_ANALYZE_SYSTEM_EXPANDED.format(locale=locale)
        user_message = (
            f"Lab results (last {ANALYSIS_DAYS} days), newest first:\n{labs_text}\n\n"
            f"Active medication schedules:\n{sched_text}\n\n"
            "Analyze the results and give practical recommendations where useful."
        )
    else:
        system_prompt = HEALTH_ANALYZE_SYSTEM_SAFE.format(locale=locale)
        user_message = (
            f"Lab results (last {ANALYSIS_DAYS} days), newest first:\n{labs_text}\n\n"
            "Restate the facts and list questions for a doctor. No recommendations."
        )

    result = await client.call_llm(
        config=llm_config,
        system_prompt=system_prompt,
        user_message=user_message,
        json_mode=True,
    )
    raw_response = result["content"]
    usage = result["usage"]

    parsed = parse_llm_json(raw_response, is_last_attempt=True)
    if not isinstance(parsed, dict):
        parsed = {}

    # sanitize: only known string-list keys, cap lengths
    out: dict = {
        "summary": "",
        "observations": [],
        "assumptions": [],
        "questions_for_doctor": [],
        "recommendations": [],
    }
    summary = parsed.get("summary")
    if isinstance(summary, str):
        out["summary"] = summary[:2000]
    for key in ("observations", "assumptions", "questions_for_doctor", "recommendations"):
        items = parsed.get(key)
        if isinstance(items, list):
            out[key] = [str(i)[:500] for i in items if isinstance(i, str | int | float)][:20]

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()

    out["_usage"] = usage
    out["_mode"] = llm_mode
    return out
