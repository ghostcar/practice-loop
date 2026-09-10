"""Page context builder and today's schedule summary."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import (
    COURSE_STATUSES,
    FOOD_RELATIONS,
    FREQUENCY_TYPES,
    INTAKE_STATUSES,
    MED_KINDS,
    MedCourse,
    Medication,
    MedIntake,
    MedKit,
    MedSchedule,
    MedStock,
)
from app.services.med.course import course_summary
from app.services.med.graph import med_matches_query
from app.services.med.regimen import (
    EXPIRING_SOON_DAYS,
    FOOD_RELATION_LABELS,
    REGIMEN_PRESETS,
    doses_today,
    group_meds_by_meal,
    intake_slots_for_schedule,
    regimen_to_text,
    schedule_times,
)
from app.services.med.serializers import med_dict
from app.services.med.substances import get_substances, normalize_substance
from app.services.med.units import (
    daily_limit_exceedances,
    equivalent_candidates,
    kit_location_label,
    location_path,
)
from app.timeutils import local_date, local_today


async def schedule_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Today: schedules with pending doses + sufficiency/substitution + daily limits."""
    today = local_today()
    schedules = (
        (
            await db.execute(
                select(MedSchedule)
                .outerjoin(MedCourse, MedSchedule.course_id == MedCourse.id)
                .where(
                    MedSchedule.user_id == user_id,
                    MedSchedule.is_active.is_(True),
                    or_(MedSchedule.course_id.is_(None), MedCourse.is_active.is_(True)),
                )
                .order_by(MedSchedule.created_at)
            )
        )
        .scalars()
        .all()
    )
    stocks = (
        (await db.execute(select(MedStock).where(MedStock.user_id == user_id, MedStock.quantity > 0))).scalars().all()
    )
    kits = (await db.execute(select(MedKit).where(MedKit.user_id == user_id))).scalars().all()
    kits_by_id = {str(k.id): k for k in kits}
    stocks_by_med: dict[str, list[MedStock]] = {}
    for st in stocks:
        stocks_by_med.setdefault(str(st.medication_id), []).append(st)

    meds = (
        (await db.execute(select(Medication).where(Medication.is_active.is_(True), Medication.user_id == user_id)))
        .scalars()
        .all()
    )
    med_by_id = {str(m.id): m for m in meds}

    intakes = (
        (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id).order_by(MedIntake.created_at.desc())))
        .scalars()
        .all()
    )

    limits = daily_limit_exceedances(meds, schedules, stocks, today)
    exceed_med_ids: set[str] = set()
    warn_med_ids: set[str] = set()
    for entry in limits.get("warnings", []):
        for r in entry.get("meds", []):
            exceed_med_ids.add(r["medication_id"])
    for entry in limits.get("allowed", []):
        for r in entry.get("meds", []):
            warn_med_ids.add(r["medication_id"])

    taken_today: dict[str, int] = {}
    taken_by_hour: dict[tuple[str, int], bool] = {}

    for it in intakes:
        if it.status != "taken" or it.schedule_id is None:
            continue
        taken_dt = it.taken_at or it.created_at
        if taken_dt is not None and local_date(taken_dt) == today:
            taken_today[str(it.schedule_id)] = taken_today.get(str(it.schedule_id), 0) + 1
            taken_by_hour[(str(it.schedule_id), taken_dt.hour)] = True

    equiv_cache: dict[str, list[dict]] = {}

    def _row_stock(s: MedSchedule, expected: int) -> dict:
        med = med_by_id.get(str(s.medication_id)) or s.medication
        stock_total = sum(
            float(st.quantity or 0)
            for st in stocks_by_med.get(str(s.medication_id), [])
            if st.expiry_date is None or st.expiry_date >= today
        )
        needed_today = round(expected * float(s.dose_quantity or 1.0), 3)
        insufficient = stock_total < needed_today
        substitute = None
        if insufficient and med is not None:
            if str(med.id) not in equiv_cache:
                equiv_cache[str(med.id)] = equivalent_candidates(med, meds, stocks_by_med)
            for cand in equiv_cache[str(med.id)]:
                if cand["match"] == "auto":
                    ratio = cand.get("qty_ratio_per_unit")
                    qty = float(s.dose_quantity or 1.0) * ratio if ratio is not None else float(s.dose_quantity or 1.0)
                    substitute = {
                        "medication_id": cand["medication_id"],
                        "name": cand["name"],
                        "form": cand["form"],
                        "strength": cand["strength"],
                        "composition_label": cand["composition_label"],
                        "stock_total": cand["stock_total"],
                        "qty_per_intake": round(qty, 3),
                    }
                    break
        return {
            "medication_id": str(s.medication_id),
            "medication_name": med.name if med else "",
            "stock_total": stock_total,
            "stock_needed_today": needed_today,
            "insufficient": insufficient,
            "substitute": substitute,
            "exceeds_daily": str(s.medication_id) in exceed_med_ids,
            "ul_pending": str(s.medication_id) in warn_med_ids,
        }

    due = []
    slots: dict[str, list] = {}
    for s in schedules:
        expected = doses_today(s, today)
        if expected <= 0:
            continue
        done = taken_today.get(str(s.id), 0)
        pending = max(0, expected - done)
        dose = f"{s.dose_quantity:g} {s.dose_unit or ''}".strip()
        extra = _row_stock(s, expected)
        dose_val = float(s.dose_quantity or 1.0)
        med_stocks = stocks_by_med.get(str(s.medication_id), [])
        available_kits = []
        preferred_stock_total = 0.0
        for st in med_stocks:
            if st.expiry_date is not None and st.expiry_date < today:
                continue
            k_obj = kits_by_id.get(str(st.kit_id)) if st.kit_id else None
            k_name = k_obj.name if k_obj else "Без аптечки"
            if s.preferred_kit_id and st.kit_id == s.preferred_kit_id:
                preferred_stock_total += float(st.quantity or 0)
            available_kits.append({
                "kit_id": str(st.kit_id) if st.kit_id else "",
                "kit_name": k_name,
                "quantity": round(float(st.quantity or 0), 2),
            })
        has_preferred_kit = bool(s.preferred_kit_id)
        preferred_kit_exhausted = bool(has_preferred_kit and preferred_stock_total < dose_val)
        no_kit = not has_preferred_kit
        needs_kit_selection = no_kit or preferred_kit_exhausted

        kit_info = {
            "food_relation": s.food_relation or "independent",
            "food_relation_label": FOOD_RELATION_LABELS.get(s.food_relation or "independent", "Независимо"),
            "meal_offset_min": s.meal_offset_min,
            "preferred_kit_id": str(s.preferred_kit_id) if s.preferred_kit_id else None,
            "preferred_kit_name": s.preferred_kit.name if s.preferred_kit else None,
            "preferred_stock_total": preferred_stock_total,
            "preferred_kit_exhausted": preferred_kit_exhausted,
            "no_kit": no_kit,
            "needs_kit_selection": needs_kit_selection,
            "available_kits": available_kits,
            "kit_location": s.preferred_kit.location if (s.preferred_kit and s.preferred_kit.location) else None,
            "instructions": s.instructions or "",
        }
        if pending > 0:
            due.append(
                {
                    "id": str(s.id),
                    **extra,
                    **kit_info,
                    "dose": dose,
                    "pending": pending,
                    "times_of_day": schedule_times(s) or s.times_of_day,
                }
            )
        times = intake_slots_for_schedule(s, today) or [""]
        if times == [""]:
            times = ["any"]
        for tm in times:
            hour = int(tm.split(":")[0]) if ":" in tm else None
            if hour is not None:
                taken = taken_by_hour.get((str(s.id), hour), False)
            else:
                taken = taken_today.get(str(s.id), 0) > 0
            slots.setdefault(tm, []).append(
                {
                    "schedule_id": str(s.id),
                    **extra,
                    **kit_info,
                    "dose": dose,
                    "taken": taken,
                    "pending": pending,
                    "times_of_day": schedule_times(s) or s.times_of_day,
                }
            )
    slot_list = [
        {
            "time": k,
            "meds": v,
            "meal_groups": group_meds_by_meal(v),
            "all_taken": all(m["taken"] for m in v),
            "pending": any(not m["taken"] for m in v),
        }
        for k, v in sorted(slots.items(), key=lambda kv: (kv[0] == "any", kv[0]))
    ]

    expiring = []
    low = []
    for st in stocks:
        if st.expiry_date is not None:
            delta = (st.expiry_date - today).days
            if delta <= EXPIRING_SOON_DAYS:
                expiring.append(
                    {
                        "id": str(st.id),
                        "medication_name": st.medication.name if st.medication else "",
                        "expiry_date": st.expiry_date.isoformat(),
                        "days": delta,
                    }
                )
        if st.low_stock_threshold is not None and st.quantity <= st.low_stock_threshold:
            low.append(
                {
                    "id": str(st.id),
                    "medication_name": st.medication.name if st.medication else "",
                    "quantity": st.quantity,
                    "threshold": st.low_stock_threshold,
                }
            )

    return {
        "due": due,
        "slots": slot_list,
        "expiring": expiring,
        "low_stock": low,
        "limits": limits,
        "today": today.isoformat(),
    }


async def get_med_page_context(
    db: AsyncSession,
    user,
    *,
    migrated: int = 0,
    skipped: int = 0,
    t: dict | None = None,
    q: str = "",
) -> dict:
    """Build full template context for GET /medications page."""
    meds_all = (
        (await db.execute(select(Medication).where(Medication.user_id == user.id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    q = (q or "").strip()
    if q:
        ql = q.lower()
        meds_all = [m for m in meds_all if med_matches_query(m, ql)]
    kits = (await db.execute(select(MedKit).where(MedKit.user_id == user.id).order_by(MedKit.name))).scalars().all()
    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user.id))).scalars().all()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user.id))).scalars().all()
    summary = await schedule_summary(db, user.id)

    t = t or {}
    stocks_by_med: dict[str, list] = {}
    stocks_by_kit: dict[str, list] = {}
    stocks_obj_by_med: dict[str, list] = {}
    for st in stocks:
        stocks_obj_by_med.setdefault(str(st.medication_id), []).append(st)
        stocks_by_med.setdefault(str(st.medication_id), []).append(
            {
                "id": str(st.id),
                "quantity": st.quantity,
                "unit": st.unit,
                "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
                "lot_number": st.lot_number,
                "kit_name": st.kit.name if st.kit else "",
                "low_stock_threshold": st.low_stock_threshold,
                "is_expired": st.expiry_date is not None and st.expiry_date < local_today(),
            }
        )
        if st.kit_id:
            stocks_by_kit.setdefault(str(st.kit_id), []).append(
                {
                    "id": str(st.id),
                    "medication_id": str(st.medication_id),
                    "medication_name": st.medication.name if st.medication else "",
                    "form": st.medication.form if st.medication else "",
                    "strength": st.medication.strength if st.medication else "",
                    "quantity": st.quantity,
                    "unit": st.unit or (st.medication.unit if st.medication else "шт"),
                    "lot_number": st.lot_number or "",
                    "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
                    "expiry_date_raw": st.expiry_date,
                    "is_expired": st.expiry_date is not None and st.expiry_date < local_today(),
                    "is_unstocked": (st.quantity or 0) <= 0,
                    "low_stock_threshold": st.low_stock_threshold,
                    "notes": st.notes or "",
                }
            )
    schedules_by_med: dict[str, list] = {}
    for s in schedules:
        schedules_by_med.setdefault(str(s.medication_id), []).append(
            {
                "id": str(s.id),
                "dose": f"{s.dose_quantity:g} {s.dose_unit or ''}".strip(),
                "frequency_type": s.frequency_type,
                "times_per_day": s.times_per_day,
                "times_of_day": s.times_of_day,
                "times": schedule_times(s),
                "interval_hours": s.interval_hours,
                "days_of_week": s.days_of_week,
                "start_date": s.start_date.isoformat() if s.start_date else None,
                "end_date": s.end_date.isoformat() if s.end_date else None,
                "food_relation": s.food_relation,
                "duration_days": s.duration_days,
                "meal_offset_min": s.meal_offset_min,
                "regimen_text": regimen_to_text(s, t),
                "is_active": s.is_active,
            }
        )

    equiv_cache: dict[str, list[dict]] = {}

    def _equivalents_for(m) -> list[dict]:
        if str(m.id) not in equiv_cache:
            equiv_cache[str(m.id)] = equivalent_candidates(m, meds_all, stocks_obj_by_med)
        return equiv_cache[str(m.id)]

    meds_data = []
    for m in meds_all:
        d = med_dict(m)
        d["stocks"] = stocks_by_med.get(str(m.id), [])
        d["schedules"] = schedules_by_med.get(str(m.id), [])
        cands = _equivalents_for(m)
        d["equivalents"] = cands[:5]
        d["equivalents_count"] = len(cands)
        meds_data.append(d)

    substance_groups: dict[str, dict] = {}
    for d in meds_data:
        total_stock = round(sum(float(st["quantity"] or 0) for st in d["stocks"]), 3)
        for comp in d["components"]:
            sub_name = comp["substance"]
            if not sub_name:
                continue
            key = normalize_substance(sub_name)
            group = substance_groups.get(key)
            if group is None:
                group = {"name": sub_name, "inn": comp.get("inn"), "meds": []}
                substance_groups[key] = group
            if not any(x["medication_id"] == d["id"] for x in group["meds"]):
                group["meds"].append(
                    {
                        "medication_id": d["id"],
                        "name": d["name"],
                        "form": d["form"],
                        "strength": d["strength"],
                        "stock_total": total_stock,
                    }
                )
    substance_groups_list = sorted(
        (
            {
                "name": g["name"],
                "inn": g["inn"],
                "meds": sorted(g["meds"], key=lambda x: x["name"].lower()),
            }
            for g in substance_groups.values()
        ),
        key=lambda g: g["name"].lower(),
    )

    from app.models.life import InventoryItem

    migrated_count_result = await db.execute(
        select(func.count(InventoryItem.id)).where(
            InventoryItem.user_id == user.id, InventoryItem.migrated_to_medication.is_(True)
        )
    )
    migrated_count = migrated_count_result.scalar() or 0

    today = local_today()
    kits_data = []
    for k in kits:
        kit_stocks = stocks_by_kit.get(str(k.id), [])
        expiries = [x["expiry_date_raw"] for x in kit_stocks if x.get("expiry_date_raw") is not None]
        sorted_items = sorted(kit_stocks, key=lambda x: x["medication_name"].lower())
        unstocked_count = sum(1 for x in kit_stocks if (x.get("quantity") or 0) <= 0)
        kits_data.append(
            {
                "id": str(k.id),
                "name": k.name,
                "location": kit_location_label(k),
                "location_id": str(k.location_id) if k.location_id else None,
                "location_path": kit_location_label(k),
                "notes": k.notes,
                "med_count": len(kit_stocks),
                "unstocked_count": unstocked_count,
                "stocked_count": len(kit_stocks) - unstocked_count,
                "meds": sorted({x["medication_name"] for x in kit_stocks if x["medication_name"]}),
                "nearest_expiry": min(expiries).isoformat() if expiries else None,
                "is_expired": bool(expiries) and min(expiries) < today,
                "items": sorted_items,
            }
        )

    courses = (
        (await db.execute(select(MedCourse).where(MedCourse.user_id == user.id).order_by(MedCourse.created_at.desc())))
        .scalars()
        .all()
    )
    courses_data = [await course_summary(db, c) for c in courses]

    from app.models.task_location import TaskLocation

    locs = (
        (
            await db.execute(
                select(TaskLocation).where(
                    TaskLocation.is_active.is_(True),
                    or_(TaskLocation.owner_id.is_(None), TaskLocation.owner_id == user.id),
                )
            )
        )
        .scalars()
        .all()
    )
    locs_data = [{"id": str(loc.id), "path": location_path(loc), "is_custom": loc.is_custom} for loc in locs]

    substances = await get_substances(db, user.id)

    return {
        "meds": meds_data,
        "substance_groups": substance_groups_list,
        "substances": substances,
        "search_q": q,
        "kits": kits_data,
        "courses": courses_data,
        "locations": locs_data,
        "summary": summary,
        "kinds": list(MED_KINDS),
        "intake_statuses": list(INTAKE_STATUSES),
        "frequency_types": list(FREQUENCY_TYPES),
        "food_relations": list(FOOD_RELATIONS),
        "course_statuses": list(COURSE_STATUSES),
        "regimen_presets": REGIMEN_PRESETS,
        "migrated": migrated,
        "skipped": skipped,
        "migrated_count": migrated_count,
    }
