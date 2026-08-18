"""LLM pipeline — Personal Insights (Шаг 17, ADR-093).

Кросс-модульный анализ личных данных (PRODUCT_OVERVIEW §12): тенденции и связи
между активностями (Tracker), Chastity Timer, сексуальной жизнью (Journal),
состоянием (Health), уходом (Care), тренировками и диетами.

Правила:
- анализ запускается **явно** (пользователь выбирает разделы и период);
- контекст собирается только из выбранных разделов за выбранный период;
- промпт требует показывать использованные данные и **не объявлять
  корреляцию причиной**;
- режим ``prefs.llm_mode`` (safe/expanded, ADR-087) расширяет рамку.

Usage трекается на активном LLMProviderConfig (tokens + cost), как в остальных
LLM-пайплайнах. Результат возвращается словарём; сохранение (insight_runs /
insight_findings) делает вызывающий слой.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import client
from app.llm.insights_prompts import INSIGHTS_SYSTEM
from app.llm.mode import llm_mode_hint
from app.llm.repair import parse_llm_json
from app.models.activity_log import ActivityLog
from app.models.care import CareEntry, CareEntryProduct, CareProduct
from app.models.diet import DietEvaluation
from app.models.health import HealthState, LabRecord
from app.models.insights import INSIGHT_SECTIONS
from app.models.journal import JournalEntry
from app.models.llm_config import LLMProviderConfig
from app.models.locktimer import LockSession
from app.models.training import TrainingDay

logger = logging.getLogger(__name__)

MAX_DAYS = 730  # период анализа ограничен 2 годами


def _fmt_num(v: float | int | None, nd: int = 1) -> str:
    if v is None:
        return "n/a"
    return f"{v:.{nd}f}"


# ─────────────────────────────────────────────────────────────────────────────
# Context builder — собирает агрегаты выбранных разделов за период
# ─────────────────────────────────────────────────────────────────────────────


async def _ctx_tracker(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> list[str]:
    rows = (
        (
            await db.execute(
                select(ActivityLog).where(
                    ActivityLog.user_id == user_id,
                    func.date(ActivityLog.created_at) >= start,
                    func.date(ActivityLog.created_at) <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    total = len(rows)
    completed = sum(1 for r in rows if r.status == "completed")
    interrupted = sum(1 for r in rows if r.status == "interrupted")
    rate = completed / total * 100 if total else 0
    by_entity: dict[str, int] = {}
    for r in rows:
        name = (r.selected_entity_name or r.entity.real_name if r.entity else None) or "?"
        by_entity[name] = by_entity.get(name, 0) + 1
    top = ", ".join(f"{k} ({v})" for k, v in sorted(by_entity.items(), key=lambda kv: -kv[1])[:5])
    return [
        f"tasks total: {total}",
        f"completed: {completed} ({_fmt_num(rate, 0)}%)",
        f"interrupted: {interrupted}",
        f"top activities: {top or '-'}",
    ]


async def _ctx_timer(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> list[str]:
    rows = (
        (
            await db.execute(
                select(LockSession).where(
                    LockSession.owner_id == user_id,
                    LockSession.started_at.isnot(None),
                    func.date(LockSession.started_at) >= start,
                    func.date(LockSession.started_at) <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    started = len(rows)
    safety = sum(1 for r in rows if r.state == "safety_stopped")
    durations = [
        (r.effective_end_at - r.started_at).total_seconds() / 3600
        for r in rows
        if r.effective_end_at and r.started_at and r.effective_end_at > r.started_at
    ]
    avg_h = sum(durations) / len(durations) if durations else None
    total_h = sum(durations) if durations else None
    return [
        f"sessions started: {started}",
        f"safety-stopped: {safety}",
        f"avg duration: {_fmt_num(avg_h)} h",
        f"total locked time: {_fmt_num(total_h)} h",
    ]


async def _ctx_journal(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> list[str]:
    rows = (
        (
            await db.execute(
                select(JournalEntry).where(
                    JournalEntry.user_id == user_id,
                    JournalEntry.entry_date >= start,
                    JournalEntry.entry_date <= end,
                    JournalEntry.status == "completed",
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    sats = [r.satisfaction for r in rows if r.satisfaction is not None]
    ints = [r.intensity for r in rows if r.intensity is not None]
    orgasms = sum(r.orgasms or 0 for r in rows)
    return [
        f"journal entries: {len(rows)}",
        f"avg satisfaction (1-5): {_fmt_num(sum(sats)/len(sats) if sats else None)}",
        f"avg intensity (1-5): {_fmt_num(sum(ints)/len(ints) if ints else None)}",
        f"orgasms total: {orgasms}",
    ]


async def _ctx_health(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> list[str]:
    states = (
        (
            await db.execute(
                select(HealthState).where(
                    HealthState.user_id == user_id,
                    HealthState.event_date >= start,
                    HealthState.event_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    labs_count = (
        await db.execute(
            select(func.count(LabRecord.id)).where(
                LabRecord.user_id == user_id,
                func.date(LabRecord.measured_at) >= start,
                func.date(LabRecord.measured_at) <= end,
            )
        )
    ).scalar() or 0
    if not states:
        if labs_count:
            return [f"lab records: {labs_count}"]
        return []

    def _avg(vals: list) -> float | None:
        return sum(vals) / len(vals) if vals else None

    moods = [s.mood for s in states if s.mood is not None]
    energies = [s.energy for s in states if s.energy is not None]
    sleeps = [s.sleep_hours for s in states if s.sleep_hours is not None]
    recovs = [s.recovery for s in states if s.recovery is not None]
    return [
        f"check-ins: {len(states)}",
        f"avg mood (1-5): {_fmt_num(_avg(moods))}",
        f"avg energy (1-5): {_fmt_num(_avg(energies))}",
        f"avg sleep: {_fmt_num(_avg(sleeps))} h",
        f"avg recovery (1-5): {_fmt_num(_avg(recovs))}",
        f"lab records: {labs_count}",
    ]


async def _ctx_care(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> list[str]:
    rows = (
        (
            await db.execute(
                select(CareEntry).where(
                    CareEntry.user_id == user_id,
                    CareEntry.entry_date >= start,
                    CareEntry.entry_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    routines = {str(e.routine_id) for e in rows if e.routine_id}
    lines = [f"care entries: {len(rows)}", f"distinct routines: {len(routines)}"]
    # Средства (ADR-094): какие средства использовались и сколько раз,
    # расходники на исходе (низкий остаток / истёкший срок).
    try:
        entry_ids = [e.id for e in rows]
        if entry_ids:
            usage_rows = (
                await db.execute(
                    select(CareEntryProduct.product_id, func.count(CareEntryProduct.id))
                    .where(CareEntryProduct.entry_id.in_(entry_ids))
                    .group_by(CareEntryProduct.product_id)
                )
            ).all()
            if usage_rows:
                products = {
                    str(p.id): p
                    for p in (
                        (await db.execute(select(CareProduct).where(CareProduct.user_id == user_id))).scalars().all()
                    )
                }
                used = [
                    f"{products.get(str(pid)).name if products.get(str(pid)) else '?'} x{count}"
                    for pid, count in usage_rows
                ]
                lines.append(f"products used: {', '.join(used)}")
                low_stock = [p.name for p in products.values() if p.quantity is not None and p.quantity <= 1]
                if low_stock:
                    lines.append(f"low stock products: {', '.join(low_stock)}")
    except Exception:
        logger.warning("care products context skipped", exc_info=True)
    return lines


async def _ctx_training(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> list[str]:
    rows = (
        (
            await db.execute(
                select(TrainingDay).where(
                    TrainingDay.user_id == user_id,
                    TrainingDay.target_date >= start,
                    TrainingDay.target_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    done = sum(1 for r in rows if r.status == "completed")
    return [f"training days: {len(rows)}", f"completed: {done}"]


async def _ctx_diet(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> list[str]:
    rows = (
        (
            await db.execute(
                select(DietEvaluation).where(
                    DietEvaluation.user_id == user_id,
                    func.date(DietEvaluation.created_at) >= start,
                    func.date(DietEvaluation.created_at) <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    scores = [r.score for r in rows if r.score is not None]
    return [
        f"diet evaluations: {len(rows)}",
        f"avg adherence score (0-100): {_fmt_num(sum(scores)/len(scores) if scores else None, 0)}",
    ]


async def _ctx_cycle(db: AsyncSession, user_id: uuid.UUID, start: date, end: date) -> list[str]:
    """Cycle-контекст: фаза по дням периода + корреляция с журналом/уходом/настроением.

    Не объявляет фазу фактом (расчётная, §9.4) и не утверждает причинность —
    только агрегаты по фазам, чтобы LLM мог сопоставить тенденции.
    """
    from app.models.health import CycleEvent, CycleSettings, HealthState
    from app.models.journal import JournalEntry

    settings = (await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))).scalar_one_or_none()
    events = (await db.execute(select(CycleEvent).where(CycleEvent.user_id == user_id))).scalars().all()
    if not events and not settings:
        return []

    cycle_length = settings.cycle_length if settings else 28
    period_length = settings.period_length if settings else 5

    # День цикла для каждого дня периода — считаем от последнего начала кровотечения.
    def _day_of_cycle_for(d: date) -> int | None:
        bleeds = sorted((e.event_date for e in events if e.event_type == "bleeding"), key=lambda x: x)
        if not bleeds:
            return None
        start_bleed = None
        prev = None
        for b in bleeds:
            if prev is None or (b - prev).days >= 3:
                start_bleed = b
            prev = b
        if start_bleed is None:
            return None
        delta = (d - start_bleed).days
        return (delta % cycle_length) + 1

    from app.api.health import _cycle_phase  # reuse the canonical phase helper

    # агрегаты по фазам: настроение (health), удовлетворённость (journal), реакция кожи (care)
    moods: dict[str, list] = {}
    satisf: dict[str, list] = {}
    skin: dict[str, list] = {}
    journal_count = 0
    states = (
        (
            await db.execute(
                select(HealthState).where(
                    HealthState.user_id == user_id,
                    HealthState.event_date >= start,
                    HealthState.event_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    for s in states:
        day = _day_of_cycle_for(s.event_date)
        if day is None:
            continue
        phase = _cycle_phase(day, cycle_length, period_length)
        if s.mood is not None:
            moods.setdefault(phase, []).append(s.mood)
    journals = (
        (
            await db.execute(
                select(JournalEntry).where(
                    JournalEntry.user_id == user_id,
                    JournalEntry.entry_date >= start,
                    JournalEntry.entry_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    for j in journals:
        day = _day_of_cycle_for(j.entry_date)
        if day is None:
            continue
        journal_count += 1
        phase = _cycle_phase(day, cycle_length, period_length)
        if j.satisfaction is not None:
            satisf.setdefault(phase, []).append(j.satisfaction)
    from app.models.care import CareEntry

    care_rows = (
        (
            await db.execute(
                select(CareEntry).where(
                    CareEntry.user_id == user_id,
                    CareEntry.entry_date >= start,
                    CareEntry.entry_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    for c in care_rows:
        day = _day_of_cycle_for(c.entry_date)
        if day is None:
            continue
        phase = _cycle_phase(day, cycle_length, period_length)
        if c.skin_reaction is not None:
            skin.setdefault(phase, []).append(c.skin_reaction)

    def _avg(vals: list) -> float | None:
        return sum(vals) / len(vals) if vals else None

    bleeds_in_period = sum(1 for e in events if start <= e.event_date <= end and e.event_type == "bleeding")
    lines: list[str] = [
        f"cycle: length {cycle_length}, period {period_length} days",
        f"bleeding events in period: {bleeds_in_period}",
    ]
    for phase in ("menstrual", "follicular", "ovulation", "luteal"):
        parts = []
        if moods.get(phase):
            parts.append(f"mood {_fmt_num(_avg(moods[phase]))} (n={len(moods[phase])})")
        if satisf.get(phase):
            parts.append(f"satisfaction {_fmt_num(_avg(satisf[phase]))} (n={len(satisf[phase])})")
        if skin.get(phase):
            parts.append(f"skin {_fmt_num(_avg(skin[phase]))} (n={len(skin[phase])})")
        if parts:
            lines.append(f"{phase}: {', '.join(parts)}")
    if journal_count:
        lines.append(f"journal entries in period: {journal_count}")
    return lines


_CONTEXT_BUILDERS = {
    "tracker": _ctx_tracker,
    "timer": _ctx_timer,
    "journal": _ctx_journal,
    "health": _ctx_health,
    "care": _ctx_care,
    "training": _ctx_training,
    "diet": _ctx_diet,
    "cycle": _ctx_cycle,
}


async def build_insights_context(
    db: AsyncSession,
    user_id: uuid.UUID,
    sections: list[str],
    period_start: date,
    period_end: date,
) -> dict[str, list[str]]:
    """Собрать агрегаты выбранных разделов за период (только с данными)."""
    out: dict[str, list[str]] = {}
    for section in sections:
        if section not in _CONTEXT_BUILDERS:
            continue
        try:
            data = await _CONTEXT_BUILDERS[section](db, user_id, period_start, period_end)
        except Exception as exc:  # модуль может быть недоступен/нет данных
            logger.warning("insights: section %s skipped: %s", section, exc)
            continue
        if data:
            out[section] = data
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Main entry
# ─────────────────────────────────────────────────────────────────────────────


async def analyze_insights(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    sections: list[str],
    period_start: date,
    period_end: date,
    locale: str = "en",
    llm_mode: str | None = None,
) -> dict:
    """Run a cross-module insights analysis via LLM.

    Returns ``{"summary": str, "findings": [ {section,title,summary,used_data} ],
    "used_sections": [...], "_usage": {...}, "_mode": str}``. Tracks usage on
    ``llm_config``. Stateless — persistence is done by the caller.
    """
    sections = [s for s in sections if s in INSIGHT_SECTIONS] or list(INSIGHT_SECTIONS)
    start = min(period_start, period_end)
    end = max(period_start, period_end)
    if (end - start).days > MAX_DAYS:
        start = end - timedelta(days=MAX_DAYS)

    context = await build_insights_context(db, user_id, sections, start, end)
    if not context:
        return {
            "summary": "",
            "findings": [],
            "used_sections": [],
            "_usage": {"total_tokens": 0, "cost": 0.0},
            "_mode": (llm_mode or "safe"),
            "_empty": True,
        }

    sections_text = "\n\n".join(
        f"## {section}\n" + "\n".join(f"- {line}" for line in lines) for section, lines in context.items()
    )
    mode = llm_mode or "safe"
    system_prompt = INSIGHTS_SYSTEM.format(locale=locale) + llm_mode_hint(mode)
    user_message = (
        f"Period: {start.isoformat()} .. {end.isoformat()}\n"
        f"Selected sections with data:\n{sections_text}\n\n"
        "Analyze trends and cross-section connections. Do not claim causation."
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

    summary = parsed.get("summary")
    if not isinstance(summary, str):
        summary = ""

    findings: list[dict] = []
    raw_findings = parsed.get("findings")
    if isinstance(raw_findings, list):
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            section = str(item.get("section", ""))[:30]
            title = str(item.get("title", ""))[:200]
            body = item.get("summary")
            if not isinstance(body, str):
                continue
            used = item.get("used_data")
            if not isinstance(used, list):
                used = []
            used = [str(u)[:500] for u in used if isinstance(u, str | int | float)][:10]
            if section and title and body:
                findings.append({"section": section, "title": title, "summary": body[:2000], "used_data": used})

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()

    return {
        "summary": summary[:3000],
        "findings": findings,
        "used_sections": list(context.keys()),
        "_usage": usage,
        "_mode": mode,
    }
