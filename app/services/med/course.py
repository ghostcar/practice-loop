"""Course CRUD (ADR-189, phase C)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import (
    COURSE_STATUSES,
    MedCourse,
    Medication,
    MedIntake,
    MedSchedule,
    MedStock,
)
from app.services.errors import NotFoundError
from app.services.med.regimen import (
    course_days,
    group_meds_by_meal,
    intake_slots_for_schedule,
    intakes_per_day,
    regimen_to_text,
)
from app.services.med.units import kit_location_label
from app.timeutils import local_today


async def get_course(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID) -> MedCourse:
    c = (
        await db.execute(select(MedCourse).where(MedCourse.id == course_id, MedCourse.user_id == user_id))
    ).scalar_one_or_none()
    if c is None:
        raise NotFoundError("Course not found")
    return c


async def create_course(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    notes: str = "",
    start_date: str = "",
) -> MedCourse:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    sd = date.fromisoformat(start_date.strip()) if start_date.strip() else None
    c = MedCourse(user_id=user_id, name=name, notes=(notes or "").strip() or None, start_date=sd)
    db.add(c)
    await db.flush()
    return c


async def delete_course(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID) -> None:
    c = await get_course(db, user_id, course_id)
    schedules = (
        await db.execute(
            select(MedSchedule).where(
                MedSchedule.course_id == course_id,
                MedSchedule.user_id == user_id,
            )
        )
    ).scalars().all()
    med_ids_to_check = {s.medication_id for s in schedules}

    for s in schedules:
        await db.delete(s)
    await db.delete(c)
    await db.flush()

    # Если препараты были созданы мастером курсов исключительно под этот курс
    # (без остатков в аптечках, других расписаний и истории приёмов), удаляем их,
    # чтобы не засорять справочник лекарств после ошибочного создания.
    for mid in med_ids_to_check:
        m = (
            await db.execute(
                select(Medication).where(Medication.id == mid, Medication.user_id == user_id)
            )
        ).scalar_one_or_none()
        if not m:
            continue
        if m.notes and (f"({c.name})" in m.notes or "Добавлено мастером курсов" in m.notes):
            has_stock = (
                await db.execute(select(MedStock.id).where(MedStock.medication_id == mid))
            ).first() is not None
            has_intake = (
                await db.execute(select(MedIntake.id).where(MedIntake.medication_id == mid))
            ).first() is not None
            has_other_sched = (
                await db.execute(select(MedSchedule.id).where(MedSchedule.medication_id == mid))
            ).first() is not None
            if not has_stock and not has_intake and not has_other_sched:
                await db.delete(m)
    await db.flush()


async def set_course_status(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID, status: str) -> MedCourse:
    c = await get_course(db, user_id, course_id)
    if status not in COURSE_STATUSES:
        raise ValueError("Invalid course status")
    c.status = status
    c.is_active = status in ("active", "planned")
    schedules = (
        await db.execute(
            select(MedSchedule).where(
                MedSchedule.course_id == course_id,
                MedSchedule.user_id == user_id,
            )
        )
    ).scalars().all()
    for s in schedules:
        s.is_active = c.is_active
    await db.flush()
    return c


async def update_course(
    db: AsyncSession,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    *,
    name: str,
    start_date: str = "",
    end_date: str = "",
    status: str = "active",
    notes: str = "",
) -> MedCourse:
    c = await get_course(db, user_id, course_id)
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    if status not in COURSE_STATUSES:
        raise ValueError("Invalid course status")
    c.name = name
    c.status = status
    c.is_active = status in ("active", "planned")
    c.notes = (notes or "").strip() or None
    c.start_date = date.fromisoformat(start_date.strip()) if start_date.strip() else None
    c.end_date = date.fromisoformat(end_date.strip()) if end_date.strip() else None
    schedules = (
        await db.execute(
            select(MedSchedule).where(
                MedSchedule.course_id == course_id,
                MedSchedule.user_id == user_id,
            )
        )
    ).scalars().all()
    for s in schedules:
        s.is_active = c.is_active
    await db.flush()
    return c


async def delete_course_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    item_id: uuid.UUID,
) -> None:
    await get_course(db, user_id, course_id)
    sched = (
        await db.execute(
            select(MedSchedule).where(
                MedSchedule.id == item_id,
                MedSchedule.course_id == course_id,
                MedSchedule.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if sched is None:
        raise NotFoundError("Course item not found")
    await db.delete(sched)
    await db.flush()


async def _course_schedules(db: AsyncSession, course_id: uuid.UUID) -> list[MedSchedule]:
    return (await db.execute(select(MedSchedule).where(MedSchedule.course_id == course_id))).scalars().all()


async def course_summary(db: AsyncSession, course: MedCourse) -> dict:
    """План + потребление + покрытие аптечками для курса."""
    schedules = await _course_schedules(db, course.id)
    items = []
    for s in schedules:
        items.append(
            {
                "id": str(s.id),
                "medication_id": str(s.medication_id),
                "medication_name": s.medication.name if s.medication else "",
                "form": s.medication.form if s.medication else "",
                "strength": s.medication.strength if s.medication else "",
                "regimen_text": regimen_to_text(s, {}),
                "dose": f"{s.dose_quantity:g} {s.dose_unit or ''}".strip(),
                "dose_quantity": s.dose_quantity,
                "dose_unit": s.dose_unit or "",
                "frequency_type": s.frequency_type,
                "times_per_day": s.times_per_day,
                "times_of_day": ", ".join(s.times_of_day) if s.times_of_day else "",
                "interval_hours": s.interval_hours,
                "days_of_week": s.days_of_week,
                "food_relation": s.food_relation or "",
                "duration_days": s.duration_days,
                "meal_offset_min": s.meal_offset_min,
                "preferred_kit_id": str(s.preferred_kit_id) if s.preferred_kit_id else None,
                "preferred_kit_name": s.preferred_kit.name if s.preferred_kit else None,
                "location": s.preferred_kit.location if (s.preferred_kit and s.preferred_kit.location) else None,
            }
        )

    grouped_slots: dict[str, list] = {}
    for s in schedules:
        times = s.times_of_day or ["any"]
        for tm in times:
            grouped_slots.setdefault(tm, []).append({
                "schedule_id": str(s.id),
                "medication_id": str(s.medication_id),
                "medication_name": s.medication.name if s.medication else "",
                "form": s.medication.form if s.medication else "",
                "strength": s.medication.strength if s.medication else "",
                "dose": f"{s.dose_quantity:g} {s.dose_unit or ''}".strip(),
                "food_relation": s.food_relation or "",
                "preferred_kit_id": str(s.preferred_kit_id) if s.preferred_kit_id else None,
                "preferred_kit_name": s.preferred_kit.name if s.preferred_kit else None,
                "location": s.preferred_kit.location if (s.preferred_kit and s.preferred_kit.location) else None,
            })
    grouped_slots_list = [
        {"slot": k, "time": k, "items": v, "meal_groups": group_meds_by_meal(v)}
        for k, v in sorted(grouped_slots.items(), key=lambda x: (x[0] == "any", x[0]))
    ]

    stocks = (
        (
            await db.execute(
                select(MedStock).where(
                    MedStock.user_id == course.user_id,
                    MedStock.medication_id.in_([s.medication_id for s in schedules]),
                )
            )
        )
        .scalars()
        .all()
        if schedules
        else []
    )
    stocks_by_med: dict[str, list] = {}
    for st in stocks:
        stocks_by_med.setdefault(str(st.medication_id), []).append(st)

    consumption = []
    for s in schedules:
        needed = round(course_days(s) * intakes_per_day(s) * s.dose_quantity, 1)
        available = sum(st.quantity for st in stocks_by_med.get(str(s.medication_id), []))
        breakdown = []
        for st in stocks_by_med.get(str(s.medication_id), []):
            breakdown.append(
                {
                    "kit_name": st.kit.name if st.kit else None,
                    "location": kit_location_label(st.kit),
                    "quantity": st.quantity,
                    "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
                }
            )
        consumption.append(
            {
                "medication_id": str(s.medication_id),
                "medication_name": s.medication.name if s.medication else "",
                "needed": needed,
                "available": available,
                "deficit": round(max(0.0, needed - available), 1),
                "unit": s.dose_unit or "",
                "stocks": breakdown,
            }
        )

    start = course.start_date or local_today()
    end = course.end_date
    if end is None and schedules:
        ends = [s.end_date for s in schedules if s.end_date]
        end = max(ends) if ends else start
    if end is None or end < start:
        end = start
    preview_days = min((end - start).days + 1, 14)
    days = []
    for i in range(preview_days):
        day = start + timedelta(days=i)
        slots: dict[str, list] = {}
        for s in schedules:
            for tm in intake_slots_for_schedule(s, day):
                slots.setdefault(tm or "any", []).append(
                    {
                        "medication_name": s.medication.name if s.medication else "",
                        "dose": f"{s.dose_quantity:g} {s.dose_unit or ''}".strip(),
                    }
                )
        days.append({"date": day.isoformat(), "slots": [{"time": k, "meds": v} for k, v in sorted(slots.items())]})

    total_days = (end - start).days + 1 if end >= start else 1
    return {
        "id": str(course.id),
        "name": course.name,
        "notes": course.notes,
        "status": course.status,
        "is_active": course.is_active,
        "start_date": course.start_date.isoformat() if course.start_date else None,
        "end_date": course.end_date.isoformat() if course.end_date else None,
        "total_days": total_days,
        "items": items,
        "grouped_slots": grouped_slots_list,
        "consumption": consumption,
        "plan": days,
    }


async def add_course_item(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    medication_id: uuid.UUID,
    dose_quantity: str = "1",
    dose_unit: str = "",
    frequency_type: str = "daily",
    times_per_day: str = "",
    times_of_day: str = "",
    interval_hours: str = "",
    days_of_week: str = "",
    food_relation: str = "",
    duration_days: str = "",
    meal_offset_min: str = "",
) -> MedSchedule:
    from app.services.med.schedule_stock_kit import create_schedule

    c = await get_course(db, user_id, course_id)
    return await create_schedule(
        db,
        user_id=user_id,
        medication_id=medication_id,
        dose_quantity=dose_quantity,
        dose_unit=dose_unit,
        frequency_type=frequency_type,
        times_per_day=times_per_day,
        times_of_day=times_of_day,
        interval_hours=interval_hours,
        days_of_week=days_of_week,
        start_date=c.start_date.isoformat() if c.start_date else "",
        end_date="",
        instructions="",
        food_relation=food_relation,
        duration_days=duration_days,
        meal_offset_min=meal_offset_min,
        course_id=str(c.id),
    )


async def batch_combine_course_slots(
    db: AsyncSession,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    schedule_ids: list[uuid.UUID],
    *,
    times_of_day: str,
    food_relation: str = "",
) -> None:
    """Объединяет выбранные препараты курса в один совместный приём (время + связь с едой)."""
    await get_course(db, user_id, course_id)
    times_list = [x.strip()[:5] for x in times_of_day.split(",") if x.strip()] if times_of_day.strip() else None
    relation = food_relation.strip() if food_relation.strip() in (
        "before_meal", "after_meal", "during_meal", "empty_stomach", "independent"
    ) else None

    stmt = select(MedSchedule).where(
        MedSchedule.course_id == course_id,
        MedSchedule.user_id == user_id,
        MedSchedule.id.in_(schedule_ids),
    )
    schedules = (await db.execute(stmt)).scalars().all()
    for s in schedules:
        if times_list is not None:
            s.times_of_day = times_list
            s.times_per_day = len(times_list)
        if relation is not None:
            s.food_relation = relation
    await db.flush()
