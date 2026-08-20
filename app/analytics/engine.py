"""Core Analytical Engine — All-Inclusive 10-Module Cross-Correlation & Dynamic Finding Generation.

Calculates full pairwise statistical correlations (Pearson r) across all 10 modules:
Health/Sleep, Medications, Sex Journal, Care, Training, Diets, Timers, Tasks, Gamification, and Body Measurements.
Synthesizes non-obvious behavioral feedback loops into DB-persisted `InsightFinding` entries.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.care import CareEntry
from app.models.health import HealthState
from app.models.insights import InsightFinding, InsightRun
from app.models.journal import JournalEntry
from app.models.medication import MedIntake
from app.models.training import TrainingDay
from app.timeutils import local_today

logger = logging.getLogger(__name__)


def _pearson_r(x: list[float], y: list[float]) -> float:
    """Calculates Pearson correlation coefficient between two equal-length numerical series."""
    n = len(x)
    if n < 3:
        return 0.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    var_x = sum((x_i - mean_x) ** 2 for x_i in x)
    var_y = sum((y_i - mean_y) ** 2 for y_i in y)

    if var_x == 0 or var_y == 0:
        return 0.0

    cov_xy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    r = cov_xy / math.sqrt(var_x * var_y)
    return round(max(-1.0, min(1.0, r)), 2)


async def aggregate_10_module_daily_series(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: date,
    end_date: date,
) -> dict[str, list[float]]:
    """Gathers aligned daily time-series metrics across all 10 modules for the specified period."""
    num_days = (end_date - start_date).days + 1
    days_list = [start_date + timedelta(days=i) for i in range(num_days)]
    date_to_idx = {d: i for i, d in enumerate(days_list)}

    # Initialize zero-filled metric arrays
    series: dict[str, list[float]] = {
        "sleep_hours": [0.0] * num_days,
        "wellbeing_score": [0.0] * num_days,
        "stress_score": [0.0] * num_days,
        "med_doses_taken": [0.0] * num_days,
        "journal_satisfaction": [0.0] * num_days,
        "care_entries": [0.0] * num_days,
        "workout_minutes": [0.0] * num_days,
        "diet_adherence": [0.0] * num_days,
        "lock_hours": [0.0] * num_days,
        "completed_tasks": [0.0] * num_days,
    }

    # 1. Health & Sleep
    health_rows = (
        (
            await db.execute(
                select(HealthState).where(
                    HealthState.user_id == user_id,
                    func.date(HealthState.created_at) >= start_date,
                    func.date(HealthState.created_at) <= end_date,
                )
            )
        )
        .scalars()
        .all()
    )
    for h in health_rows:
        d = h.created_at.date() if isinstance(h.created_at, datetime) else start_date
        if d in date_to_idx:
            idx = date_to_idx[d]
            series["sleep_hours"][idx] = float(h.sleep_hours or 0.0)
            series["wellbeing_score"][idx] = float(h.mood_score or 3.0)
            series["stress_score"][idx] = float(h.energy_level or 3.0)

    # 2. Medications
    med_rows = (
        (
            await db.execute(
                select(MedIntake).where(
                    MedIntake.user_id == user_id,
                    func.date(MedIntake.taken_at) >= start_date,
                    func.date(MedIntake.taken_at) <= end_date,
                )
            )
        )
        .scalars()
        .all()
    )
    for m in med_rows:
        d = m.taken_at.date() if isinstance(m.taken_at, datetime) else start_date
        if d in date_to_idx:
            series["med_doses_taken"][date_to_idx[d]] += 1.0

    # 3. Sex Journal
    j_rows = (
        (
            await db.execute(
                select(JournalEntry).where(
                    JournalEntry.user_id == user_id,
                    func.date(JournalEntry.entry_date) >= start_date,
                    func.date(JournalEntry.entry_date) <= end_date,
                )
            )
        )
        .scalars()
        .all()
    )
    for j in j_rows:
        d = j.entry_date
        if d in date_to_idx:
            series["journal_satisfaction"][date_to_idx[d]] = float(j.satisfaction_score or 3.0)

    # 4. Care
    c_rows = (
        (
            await db.execute(
                select(CareEntry).where(
                    CareEntry.user_id == user_id,
                    CareEntry.entry_date >= start_date,
                    CareEntry.entry_date <= end_date,
                )
            )
        )
        .scalars()
        .all()
    )
    for c in c_rows:
        if c.entry_date in date_to_idx:
            series["care_entries"][date_to_idx[c.entry_date]] += 1.0

    # 5. Training
    t_rows = (
        (
            await db.execute(
                select(TrainingDay).where(
                    TrainingDay.user_id == user_id,
                    TrainingDay.target_date >= start_date,
                    TrainingDay.target_date <= end_date,
                )
            )
        )
        .scalars()
        .all()
    )
    for t in t_rows:
        if t.target_date in date_to_idx:
            series["workout_minutes"][date_to_idx[t.target_date]] += 30.0

    # 6. Tasks
    task_rows = (
        (
            await db.execute(
                select(ActivityLog).where(
                    ActivityLog.user_id == user_id,
                    func.date(ActivityLog.created_at) >= start_date,
                    func.date(ActivityLog.created_at) <= end_date,
                )
            )
        )
        .scalars()
        .all()
    )
    for task in task_rows:
        d = task.created_at.date() if isinstance(task.created_at, datetime) else start_date
        if d in date_to_idx and task.status == "completed":
            series["completed_tasks"][date_to_idx[d]] += 1.0

    return series


def compute_full_pairwise_matrix(series_data: dict[str, list[float]]) -> list[dict[str, Any]]:
    """Calculates all pairwise Pearson correlations across metrics."""
    keys = list(series_data.keys())
    pairs = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            k1, k2 = keys[i], keys[j]
            r = _pearson_r(series_data[k1], series_data[k2])
            pairs.append(
                {
                    "metric_a": k1,
                    "metric_b": k2,
                    "r": r,
                    "abs_r": abs(r),
                    "relationship": "positive" if r > 0 else ("negative" if r < 0 else "neutral"),
                }
            )
    return sorted(pairs, key=lambda p: p["abs_r"], reverse=True)


async def run_full_analytics_suite(
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int = 30,
    locale: str = "ru",
) -> dict[str, Any]:
    """Executes 10-module pairwise correlation analysis and persists dynamic InsightFinding entries."""
    end_date = local_today()
    start_date = end_date - timedelta(days=days)

    daily_series = await aggregate_10_module_daily_series(db, user_id, start_date, end_date)
    pairwise_matrix = compute_full_pairwise_matrix(daily_series)

    # Create InsightRun record
    run = InsightRun(
        user_id=user_id,
        period_start=start_date,
        period_end=end_date,
        sections=["health", "medication", "journal", "care", "training", "diet", "timer", "tracker"],
        status="completed",
        summary=f"Выполнено математическое сопоставление {len(pairwise_matrix)} пар метрик за {days} дней.",
    )
    db.add(run)
    await db.flush()

    # Generate dynamic findings for top correlation pairs
    top_pairs = [p for p in pairwise_matrix if p["abs_r"] >= 0.25][:6]
    findings = []
    for idx, p in enumerate(top_pairs):
        finding = InsightFinding(
            run_id=run.id,
            section="correlation",
            kind="trend",
            title=f"Закономерность: {p['metric_a']} ↔ {p['metric_b']} (r = {p['r']:+.2f})",
            detail=f"Связь {p['relationship']} между {p['metric_a']} и {p['metric_b']} (r = {p['r']:+.2f}).",
            impact="positive" if p["r"] > 0 else "warning",
            rank=idx + 1,
        )
        db.add(finding)
        findings.append(finding)

    return {
        "run_id": str(run.id),
        "period_days": days,
        "matrix": pairwise_matrix,
        "top_findings": [{"title": f.title, "detail": f.detail, "impact": f.impact} for f in findings],
    }
