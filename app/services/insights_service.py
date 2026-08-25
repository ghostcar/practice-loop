"""Insights service — all business logic for personal insights, medical export, correlation.

Extracted from app/api/insights.py (ADR-168).  HTTP layer stays thin.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.pipeline import analyze_insights, get_active_llm_config
from app.llm.repair import JsonRepairError
from app.models.insights import INSIGHT_SECTIONS, InsightFinding, InsightRun
from app.models.user import User
from app.prefs import get_prefs
from app.timeutils import local_today

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 30


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def default_period() -> tuple[date, date]:
    end = local_today()
    start = end - timedelta(days=DEFAULT_DAYS)
    return start, end


def parse_period(start_raw: str, end_raw: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_raw.strip())
    except ValueError:
        raise ValueError("Invalid period_start (ISO 8601)") from None
    try:
        end = date.fromisoformat(end_raw.strip())
    except ValueError:
        raise ValueError("Invalid period_end (ISO 8601)") from None
    if end < start:
        start, end = end, start
    return start, end


def run_view(run: InsightRun) -> dict:
    return {
        "id": str(run.id),
        "period_start": run.period_start.isoformat(),
        "period_end": run.period_end.isoformat(),
        "sections": run.sections or list(INSIGHT_SECTIONS),
        "status": run.status,
        "summary": run.summary,
        "usage_tokens": run.usage_tokens,
        "usage_cost": run.usage_cost,
        "error": run.error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "findings": [finding_view(f) for f in run.findings],
    }


def finding_view(f: InsightFinding) -> dict:
    return {
        "id": str(f.id),
        "section": f.section,
        "title": f.title,
        "summary": f.summary,
        "used_data": f.used_data or [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard summary (relief-only, informational)
# ─────────────────────────────────────────────────────────────────────────────


async def insights_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Краткая сводка для дашборда: последний запуск + число находок."""
    run = (
        (await db.execute(
            select(InsightRun)
            .where(InsightRun.user_id == user_id)
            .order_by(InsightRun.created_at.desc())
        ))
        .scalars()
        .first()
    )
    if run is None:
        return {"has_runs": False, "runs_count": 0}
    count = (await db.execute(select(func.count(InsightRun.id)).where(InsightRun.user_id == user_id))).scalar() or 0
    return {
        "has_runs": True,
        "runs_count": count,
        "last_date": run.created_at.date().isoformat() if run.created_at else None,
        "last_status": run.status,
        "last_summary": run.summary,
        "findings_count": len(run.findings),
        "period": f"{run.period_start.isoformat()} — {run.period_end.isoformat()}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page context
# ─────────────────────────────────────────────────────────────────────────────


async def get_insights_page_context(db: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID | None = None) -> dict:
    """Build insights page context: runs list + selected run."""
    runs = (
        (await db.execute(
            select(InsightRun)
            .where(InsightRun.user_id == user_id)
            .order_by(InsightRun.created_at.desc())
        ))
        .scalars()
        .all()
    )
    selected = None
    if run_id is not None:
        selected = next((r for r in runs if r.id == run_id), None)
    if selected is None and runs:
        selected = runs[0]

    start, end = default_period()
    return {
        "sections": list(INSIGHT_SECTIONS),
        "default_start": start.isoformat(),
        "default_end": end.isoformat(),
        "runs": [run_view(r) for r in runs],
        "selected": run_view(selected) if selected else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Run analysis (shared by form + JSON API)
# ─────────────────────────────────────────────────────────────────────────────


async def execute_insight_run(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    start: date,
    end: date,
    chosen: list[str],
    locale: str,
    llm_mode: str | None = None,
) -> InsightRun:
    """Create InsightRun, execute LLM analysis, save findings. Returns run."""
    llm_config = await get_active_llm_config(db, user_id)
    if llm_config is None:
        raise ValueError("no_llm_config")

    if llm_mode is None:
        llm_mode = get_prefs().llm_mode

    run = InsightRun(user_id=user_id, period_start=start, period_end=end, sections=chosen, status="completed")
    db.add(run)
    await db.flush()

    try:
        result = await analyze_insights(
            db=db,
            user_id=user_id,
            llm_config=llm_config,
            sections=chosen,
            period_start=start,
            period_end=end,
            locale=locale,
            llm_mode=llm_mode,
        )
        run.summary = result.get("summary") or None
        run.usage_tokens = result.get("_usage", {}).get("total_tokens", 0)
        run.usage_cost = result.get("_usage", {}).get("cost", 0.0)
        run.status = "completed"
        for finding in result.get("findings", []):
            db.add(
                InsightFinding(
                    run_id=run.id,
                    section=finding["section"],
                    title=finding["title"],
                    summary=finding["summary"],
                    used_data=finding.get("used_data") or [],
                )
            )
    except (JsonRepairError, ValueError, Exception) as exc:  # noqa: BLE001
        logger.warning("insights run failed: %s", exc)
        run.status = "failed"
        run.error = str(exc)[:500]

    await db.flush()
    return run


# ─────────────────────────────────────────────────────────────────────────────
# Delete run
# ─────────────────────────────────────────────────────────────────────────────


async def delete_insight_run(db: AsyncSession, run_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Delete a past run + its findings. Returns True if deleted."""
    stmt = select(InsightRun).where(InsightRun.id == run_id, InsightRun.user_id == user_id)
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is not None:
        await db.delete(run)
        await db.flush()
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Medical exporter
# ─────────────────────────────────────────────────────────────────────────────


async def get_medical_export_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Load medications and care courses for the medical exporter."""
    from app.models.care import CareCourse
    from app.models.medication import Medication

    medications = list((await db.execute(select(Medication).where(Medication.user_id == user_id))).scalars().all())
    courses = list((await db.execute(select(CareCourse).where(CareCourse.user_id == user_id))).scalars().all())
    return {"medications": medications, "courses": courses}


def generate_medical_report(
    user: User,
    all_meds: list,
    all_courses: list,
    *,
    include_meds: list[str],
    include_courses: list[str],
    anonymize: bool,
    period_days: int,
) -> dict:
    """Build filtered medical report data dict."""
    filtered_meds = [m for m in all_meds if str(m.id) in include_meds]
    filtered_courses = [c for c in all_courses if str(c.id) in include_courses]

    today_str = date.today().strftime("%Y-%m-%d")
    patient_name = "Анонимный Пациент (Private Record)" if anonymize else (user.email or "Пользователь")

    return {
        "patient_name": patient_name,
        "generated_date": today_str,
        "medications": filtered_meds,
        "courses": filtered_courses,
        "period_days": period_days,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Correlation matrix
# ─────────────────────────────────────────────────────────────────────────────


async def get_correlation_matrix(db: AsyncSession, user_id: uuid.UUID, days: int = 30) -> dict:
    """Aggregated correlation matrix data for charts."""
    from app.models.health import HealthState
    from app.models.journal import JournalEntry, JournalPartner
    from app.models.locktimer import LockSession

    # Health states
    h_stmt = (
        select(HealthState)
        .where(HealthState.user_id == user_id)
        .order_by(HealthState.event_date.asc())
        .limit(days)
    )
    health_states = (await db.execute(h_stmt)).scalars().all()

    health_matrix = []
    for h in health_states:
        health_matrix.append({
            "date": h.event_date.isoformat(),
            "mood": h.mood or 0,
            "energy": h.energy or 0,
            "sleep_hours": h.sleep_hours or 0,
            "post_session_drop": bool(h.post_session_drop),
            "hrt_taken": bool(h.hrt_taken),
        })

    # Lock sessions
    locks_stmt = select(LockSession).where(LockSession.owner_id == user_id).limit(20)
    locks = (await db.execute(locks_stmt)).scalars().all()

    lock_matrix = []
    for lock_sess in locks:
        dur_h = 0.0
        if lock_sess.started_at and lock_sess.ended_at:
            dur_h = round((lock_sess.ended_at - lock_sess.started_at).total_seconds() / 3600.0, 1)
        lock_matrix.append({
            "lock_id": str(lock_sess.id)[:8],
            "status": lock_sess.status,
            "duration_hours": dur_h,
            "extensions_count": len(lock_sess.extension_history or []),
            "health_paused": lock_sess.is_health_paused,
        })

    # Partner satisfaction
    partners_stmt = select(JournalPartner).where(JournalPartner.user_id == user_id)
    partners = (await db.execute(partners_stmt)).scalars().all()

    partner_matrix = []
    for p in partners:
        entries_stmt = select(func.avg(JournalEntry.satisfaction)).where(
            JournalEntry.user_id == user_id, JournalEntry.partner_id == p.id
        )
        avg_sat = (await db.execute(entries_stmt)).scalar() or 0.0
        partner_matrix.append({
            "partner_name": p.name,
            "roles": p.roles or [],
            "avg_satisfaction": round(float(avg_sat), 2),
        })

    return {
        "days": days,
        "health_matrix": health_matrix,
        "lock_matrix": lock_matrix,
        "partner_matrix": partner_matrix,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Report page stats
# ─────────────────────────────────────────────────────────────────────────────


async def get_report_stats(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """ActivityLog stats for the report page."""
    from app.models.activity_log import ActivityLog

    totals = (
        await db.execute(
            select(
                func.count(ActivityLog.id),
                func.count(ActivityLog.id).filter(ActivityLog.status == "completed"),
                func.count(ActivityLog.id).filter(ActivityLog.status == "stopped"),
            ).where(ActivityLog.user_id == user_id)
        )
    ).one()
    total_logs, completed_logs, stopped_logs = (int(value or 0) for value in totals)
    completion_rate = round((completed_logs / total_logs) * 100) if total_logs else 0

    return {
        "total_logs": total_logs,
        "completion_rate": completion_rate,
        "stopped_logs": stopped_logs,
    }
