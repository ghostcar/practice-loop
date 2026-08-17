"""LLM diet pipeline — generation + evaluation + training synergy."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import client
from app.llm.diet_prompts import (
    DIET_EVALUATE_SYSTEM,
    DIET_GENERATE_SYSTEM,
    DIET_TRAINING_SYNERGY_SYSTEM,
)
from app.llm.mode import llm_mode_hint
from app.llm.repair import parse_llm_json
from app.models.activity_log import ActivityLog
from app.models.diet import Diet, DietConsumption, DietEvaluation, DietItem, DietTrainingReview
from app.models.llm_config import LLMProviderConfig
from app.models.training import TrainingDay
from app.timeutils import local_today

logger = logging.getLogger(__name__)

DIET_ITEM_LIMIT = 20
DIET_NAME_MAX = 200
DIET_DESC_MAX = 3000


async def generate_diet(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    locale: str = "en",
    direction: str | None = None,
    goal: str | None = None,
    preferences: str | None = None,
    llm_mode: str | None = None,
) -> Diet:
    """Generate a new diet plan via LLM (name, description, food items).

    The LLM output is sanitized before persistence: item count capped, field
    lengths clamped, quantities coerced to positive floats. The Diet is created
    only after the response parses and at least one valid item exists — a
    failed attempt never leaves a partial diet behind.
    """
    user_goal = " ".join(x for x in (direction, goal, preferences) if x) or "balanced healthy diet"
    system_prompt = DIET_GENERATE_SYSTEM.format(locale=locale) + llm_mode_hint(llm_mode)
    user_message = f"Direction/goal: {user_goal}\n\nCreate a daily diet plan."

    result = await client.call_llm(
        config=llm_config, system_prompt=system_prompt, user_message=user_message, json_mode=True
    )
    raw_response = result["content"]
    usage = result["usage"]
    parsed = parse_llm_json(raw_response, is_last_attempt=True)

    name = str(parsed.get("name") or "").strip()[:DIET_NAME_MAX]
    if not name:
        raise ValueError("LLM diet response missing name")
    description = str(parsed.get("description") or "").strip()[:DIET_DESC_MAX] or None
    raw_items = parsed.get("items", [])
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("LLM diet response has no items")

    prepared_items = []
    for it in raw_items[:DIET_ITEM_LIMIT]:
        if not isinstance(it, dict):
            continue
        item_name = str(it.get("name") or "").strip()[:300]
        if not item_name:
            continue
        qty = it.get("quantity")
        try:
            qty = float(qty) if qty not in (None, "") else None
            if qty is not None and (qty <= 0 or qty > 100_000):
                qty = None
        except (TypeError, ValueError):
            qty = None
        meal = str(it.get("meal_time") or "").strip()[:30] or None
        unit = str(it.get("unit") or "").strip()[:20] or None
        notes = str(it.get("notes") or "").strip()[:2000] or None
        prepared_items.append(
            {
                "name": item_name,
                "quantity": qty,
                "unit": unit,
                "meal_time": meal,
                "notes": notes,
            }
        )
    if not prepared_items:
        raise ValueError("LLM diet response has no usable items")

    diet = Diet(user_id=user_id, name=name, direction=direction, goal=goal, description=description, is_active=True)
    db.add(diet)
    await db.flush()
    for pos, item in enumerate(prepared_items):
        db.add(DietItem(diet_id=diet.id, sort_order=pos, **item))

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()
    return diet


async def evaluate_diet(
    db: AsyncSession,
    diet: Diet,
    llm_config: LLMProviderConfig,
    locale: str = "en",
    days: int = 7,
    llm_mode: str | None = None,
) -> dict:
    """Evaluate the user's actual consumption against a diet plan via LLM.

    Returns the parsed evaluation dict and applies sanitized plan adjustments
    (add / modify / remove of diet items matched by name). Never trusts the
    LLM with free-form item ids — matches are resolved by exact name against
    the diet's current items.
    """
    start = local_today() - timedelta(days=max(1, min(days, 30)))
    items_result = await db.execute(select(DietItem).where(DietItem.diet_id == diet.id).order_by(DietItem.sort_order))
    plan_items = list(items_result.scalars().all())
    cons_result = await db.execute(
        select(DietConsumption)
        .where(DietConsumption.user_id == diet.user_id, DietConsumption.consumed_date >= start)
        .order_by(DietConsumption.consumed_date, DietConsumption.created_at)
    )
    consumptions = list(cons_result.scalars().all())

    def _fmt_item(it: DietItem) -> str:
        qty = f"{it.quantity:g}" if it.quantity else ""
        return f"- {it.name} ({qty} {it.unit or ''}) [{it.meal_time or 'anytime'}]"

    plan_text = "\n".join(_fmt_item(it) for it in plan_items) or "- (empty plan)"
    consumed_text = (
        "\n".join(
            f"- {c.consumed_date}: {c.name} ({c.quantity or ''} {c.unit or ''}) [{c.meal_time or 'anytime'}]"
            for c in consumptions
        )
        or "- (no consumption recorded)"
    )

    system_prompt = DIET_EVALUATE_SYSTEM.format(locale=locale) + llm_mode_hint(llm_mode)
    user_message = (
        f"Diet: {diet.name} (direction: {diet.direction or '—'}, goal: {diet.goal or '—'})\n\n"
        f"Planned items:\n{plan_text}\n\n"
        f"Actual consumption (last {days} days):\n{consumed_text}\n\n"
        "Evaluate adherence and suggest plan adjustments."
    )

    result = await client.call_llm(
        config=llm_config, system_prompt=system_prompt, user_message=user_message, json_mode=True
    )
    raw_response = result["content"]
    usage = result["usage"]
    parsed = parse_llm_json(raw_response, is_last_attempt=True)

    # ── Apply sanitized adjustments ──
    by_name = {it.name.strip().lower(): it for it in plan_items}
    applied: list[dict] = []
    adjustments = parsed.get("adjustments", [])
    if isinstance(adjustments, list):
        for adj in adjustments[:10]:
            if not isinstance(adj, dict):
                continue
            action = str(adj.get("action") or "").strip().lower()
            if action == "add":
                item_name = str(adj.get("name") or "").strip()[:300]
                if not item_name:
                    continue
                try:
                    qty = float(adj.get("quantity")) if adj.get("quantity") not in (None, "") else None
                    if qty is not None and (qty <= 0 or qty > 100_000):
                        qty = None
                except (TypeError, ValueError):
                    qty = None
                max_o = await db.execute(
                    select(DietItem.sort_order)
                    .where(DietItem.diet_id == diet.id)
                    .order_by(DietItem.sort_order.desc())
                    .limit(1)
                )
                next_order = (max_o.scalar_one_or_none() or -1) + 1
                new_item = DietItem(
                    diet_id=diet.id,
                    name=item_name,
                    quantity=qty,
                    unit=str(adj.get("unit") or "").strip()[:20] or None,
                    meal_time=str(adj.get("meal_time") or "").strip()[:30] or None,
                    notes=str(adj.get("notes") or "").strip()[:2000] or None,
                    sort_order=next_order,
                )
                db.add(new_item)
                applied.append({"action": "add", "name": item_name})
            elif action in ("modify", "remove"):
                match_name = str(adj.get("match_name") or adj.get("name") or "").strip()
                target = by_name.get(match_name.lower())
                if target is None:
                    continue
                if action == "remove":
                    await db.delete(target)
                    applied.append({"action": "remove", "name": target.name})
                else:
                    try:
                        qty = float(adj.get("quantity")) if adj.get("quantity") not in (None, "") else None
                        if qty is not None and (qty <= 0 or qty > 100_000):
                            qty = None
                    except (TypeError, ValueError):
                        qty = None
                    if qty is not None:
                        target.quantity = qty
                    target.unit = str(adj.get("unit") or target.unit or "").strip()[:20] or None
                    target.meal_time = str(adj.get("meal_time") or target.meal_time or "").strip()[:30] or None
                    notes = str(adj.get("notes") or "").strip()[:2000]
                    if notes:
                        target.notes = notes
                    db.add(target)
                    applied.append({"action": "modify", "name": target.name})

    # Score & findings are only trusted as numbers/strings.
    try:
        score = max(0, min(100, float(parsed.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    summary = str(parsed.get("summary") or "").strip()[:5000] or "No summary."
    findings = [str(f)[:500] for f in parsed.get("findings", []) if isinstance(f, str)][:10]

    evaluation = {"score": score, "summary": summary, "findings": findings, "applied": applied}
    diet.last_evaluation = evaluation
    diet.evaluated_at = datetime.now(UTC)
    db.add(diet)
    # History: persist this evaluation so the user can see evolution over time.
    # created_at set in Python (not server_default) so consecutive evaluations
    # in the same SQLite transaction get distinct timestamps for stable ordering.
    db.add(
        DietEvaluation(
            diet_id=diet.id,
            user_id=diet.user_id,
            score=score,
            summary=summary,
            findings=findings or [],
            applied=applied or [],
            created_at=datetime.now(UTC),
        )
    )

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()

    return evaluation


async def analyze_diet_training_synergy(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    locale: str = "en",
    days: int = 7,
    llm_mode: str | None = None,
) -> DietTrainingReview:
    """Analyze the mutual influence between diets and training via LLM.

    Gathers the period's diet consumption + training results and asks the LLM
    to find concrete correlations and cross-domain adjustments. The result is
    persisted as a DietTrainingReview (history is kept).
    """
    period_end = local_today()
    period_start = period_end - timedelta(days=max(1, min(days, 30)) - 1)

    # Diet side: consumptions + active diet names
    cons_result = await db.execute(
        select(DietConsumption)
        .where(DietConsumption.user_id == user_id, DietConsumption.consumed_date >= period_start)
        .order_by(DietConsumption.consumed_date, DietConsumption.created_at)
    )
    consumptions = list(cons_result.scalars().all())
    diet_result = await db.execute(
        select(Diet).where(Diet.user_id == user_id, Diet.is_active.is_(True)).order_by(Diet.created_at)
    )
    active_diets = list(diet_result.scalars().all())

    # Training side: days in period + their task statuses
    day_result = await db.execute(
        select(TrainingDay)
        .where(TrainingDay.user_id == user_id, TrainingDay.target_date >= period_start)
        .order_by(TrainingDay.target_date)
    )
    training_days = list(day_result.scalars().all())
    day_ids = [td.id for td in training_days]
    logs_by_day: dict[uuid.UUID, list[ActivityLog]] = {}
    if day_ids:
        logs_result = await db.execute(
            select(ActivityLog).where(ActivityLog.training_day_id.in_(day_ids)).order_by(ActivityLog.created_at)
        )
        for log in logs_result.scalars().all():
            logs_by_day.setdefault(log.training_day_id, []).append(log)

    # ── Build the prompt ──
    diet_text = (
        "\n".join(f"- {d.name} (direction: {d.direction or '—'}, goal: {d.goal or '—'})" for d in active_diets)
        or "- (no active diets)"
    )
    consumed_text = (
        "\n".join(
            f"- {c.consumed_date}: {c.name} ({c.quantity or ''} {c.unit or ''}) [{c.meal_time or 'anytime'}]"
            for c in consumptions
        )
        or "- (no consumption recorded)"
    )
    training_lines = []
    for td in training_days:
        logs = logs_by_day.get(td.id, [])
        completed = sum(1 for lg in logs if lg.status == "completed")
        stopped = sum(1 for lg in logs if lg.status == "stopped")
        planned = sum(1 for lg in logs if lg.status == "planned")
        training_lines.append(
            f"- {td.target_date}: {len(logs)} tasks ({completed} done, {stopped} stopped, {planned} left)"
        )
    training_text = "\n".join(training_lines) or "- (no training recorded)"

    system_prompt = DIET_TRAINING_SYNERGY_SYSTEM.format(locale=locale) + llm_mode_hint(llm_mode)
    user_message = (
        f"Period: {period_start} .. {period_end}\n\n"
        f"Active diets:\n{diet_text}\n\n"
        f"What was eaten:\n{consumed_text}\n\n"
        f"Training results:\n{training_text}\n\n"
        "Analyze the mutual influence between nutrition and training."
    )

    result = await client.call_llm(
        config=llm_config, system_prompt=system_prompt, user_message=user_message, json_mode=True
    )
    usage = result["usage"]
    parsed = parse_llm_json(result["content"], is_last_attempt=True)

    # ── Sanitize ──
    summary = str(parsed.get("summary") or "").strip()[:5000] or "No analysis."
    correlations = []
    for c in parsed.get("correlations", []) or []:
        if not isinstance(c, dict):
            continue
        direction = str(c.get("direction") or "").strip()
        if direction not in ("diet_to_training", "training_to_diet"):
            direction = "diet_to_training"
        text = str(c.get("text") or "").strip()[:1000]
        if text:
            correlations.append({"direction": direction, "text": text})
    raw_adj = [str(a).strip()[:1000] for a in (parsed.get("adjustments") or []) if isinstance(a, str) and a.strip()]
    adjustments = raw_adj[:8]

    review = DietTrainingReview(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        analysis={"summary": summary, "correlations": correlations, "adjustments": adjustments},
    )
    db.add(review)
    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()
    return review
