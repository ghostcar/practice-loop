"""Intake recording, FEFO stock deduction and PRN intakes (ADR-189, ADR-190, ADR-207)."""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import INTAKE_STATUSES, MedIntake, MedStock
from app.services.med.graph import get_med, get_schedule
from app.timeutils import local_now, local_today


async def _deduct_stock_fefo(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    quantity: float,
    preferred_kit_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID | None, uuid.UUID | None, float]:
    """Списывает количество препарата по принципу FEFO строго из указанной аптечки.

    Правило безопасности (ADR-207, корректировка владельца):
    - Если аптечка не указана (preferred_kit_id is None): автосписание НЕ производится.
      Система не имеет права делать автовыбор аптечки наугад.
    - Если аптечка указана (preferred_kit_id is not None): списываем ТОЛЬКО из этой аптечки.
      Если запас в ней исчерпан (quantity <= 0) — автопереключение на другие аптечки ЗАПРЕЩЕНО.
      Списание не производится, пока пользователь явно не укажет другую аптечку.
    """
    if quantity <= 0 or preferred_kit_id is None:
        return None, preferred_kit_id, 0.0

    stmt = (
        select(MedStock)
        .where(
            MedStock.user_id == user_id,
            MedStock.medication_id == medication_id,
            MedStock.kit_id == preferred_kit_id,
            MedStock.quantity > 0,
        )
    )
    stocks = (await db.execute(stmt)).scalars().all()
    if not stocks:
        return None, preferred_kit_id, 0.0

    def _sort_key(s: MedStock):
        no_expiry = 1 if s.expiry_date is None else 0
        exp = s.expiry_date or datetime.max.date()
        return (no_expiry, exp, s.created_at)

    sorted_stocks = sorted(stocks, key=_sort_key)
    target_stock = sorted_stocks[0]

    deducted = min(target_stock.quantity, quantity)
    target_stock.quantity = round(max(0.0, target_stock.quantity - deducted), 4)
    db.add(target_stock)
    await db.flush()

    return target_stock.id, target_stock.kit_id, deducted


async def record_intake(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    schedule_id: uuid.UUID | None = None,
    status: str = "taken",
    taken_at: str | None = None,
    quantity_taken: float | None = None,
    notes: str | None = None,
    substituted_for_id: uuid.UUID | None = None,
    ul_confirmed: bool = False,
    gamification: bool = True,
    kit_id: uuid.UUID | None = None,
    is_prn: bool = False,
    deduct_stock: bool = True,
) -> MedIntake:
    """Record an intake event with automatic FEFO stock deduction and multi-kit tracking.

    ADR-190: замена препарата (substituted_for_id).
    ADR-207: автоматическое списание из MedStock по FEFO и поддержка PRN.
    """
    m = await get_med(db, user_id, medication_id)
    sched = None
    if schedule_id:
        sched = await get_schedule(db, user_id, schedule_id)
    if status not in INTAKE_STATUSES:
        status = "unknown"
    taken_dt = None
    if taken_at:
        try:
            taken_dt = datetime.fromisoformat(taken_at)
        except ValueError:
            taken_dt = None
    if status == "taken" and taken_dt is None:
        taken_dt = local_now()

    actual_qty = quantity_taken
    if actual_qty is None:
        actual_qty = float(sched.dose_quantity) if (sched and sched.dose_quantity) else 1.0

    target_kit_id = kit_id or (sched.preferred_kit_id if sched else None)
    used_stock_id = None

    notes_parts = [(notes or "").strip()]

    if status == "taken" and deduct_stock and actual_qty > 0:
        if target_kit_id:
            used_stock_id, deducted_kit_id, _ = await _deduct_stock_fefo(
                db,
                user_id=user_id,
                medication_id=m.id,
                quantity=actual_qty,
                preferred_kit_id=target_kit_id,
            )
            if used_stock_id is None:
                notes_parts.append("Запас в указанной аптечке исчерпан (автовыбор отключен — укажите аптечку вручную)")
        else:
            notes_parts.append("Аптечка не указана (автосписание отключено — выберите аптечку)")
    substituted = substituted_for_id
    if substituted is None and sched is not None and sched.medication_id != m.id:
        substituted = sched.medication_id
    if substituted is not None and substituted != m.id:
        original = await get_med(db, user_id, substituted)
        notes_parts.append(f"Замена: вместо «{original.name}» принят «{m.name}»")
    if ul_confirmed:
        notes_parts.append("Превышение суточной дозы подтверждено пользователем")
    if is_prn:
        notes_parts.append("Ситуативный приём (по требованию)")
    note_text = " · ".join(p for p in notes_parts if p) or None

    it = MedIntake(
        user_id=user_id,
        medication_id=m.id,
        schedule_id=sched.id if sched else None,
        kit_id=target_kit_id,
        stock_id=used_stock_id,
        is_prn=bool(is_prn),
        substituted_for_id=substituted if substituted != m.id else None,
        ul_confirmed=bool(ul_confirmed),
        scheduled_at=local_now(),
        taken_at=taken_dt,
        status=status,
        quantity_taken=actual_qty,
        notes=note_text,
    )
    db.add(it)
    await db.flush()
    if status == "taken" and gamification:
        from app.gamification.medication import on_medication_taken

        await on_medication_taken(db, user_id, m.name, on_time=True)
    return it


async def record_batch_intake(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    schedule_ids: list[uuid.UUID],
    slot_time: str = "",
    kit_id: uuid.UUID | None = None,
) -> int:
    """Отметить принятым целый временной слот со списанием остатков (ADR-189, ADR-207)."""
    created = 0
    for sid in schedule_ids:
        sched = await get_schedule(db, user_id, sid)
        taken_dt = local_now()
        if slot_time and ":" in slot_time:
            with contextlib.suppress(ValueError):
                taken_dt = datetime.combine(local_today(), datetime.strptime(slot_time, "%H:%M").time())
        await record_intake(
            db,
            user_id=user_id,
            medication_id=sched.medication_id,
            schedule_id=sched.id,
            status="taken",
            taken_at=taken_dt.isoformat(),
            quantity_taken=None,
            notes="",
            gamification=True,
            kit_id=kit_id or sched.preferred_kit_id,
            deduct_stock=True,
        )
        created += 1
    return created


async def record_prn_intake(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    quantity_taken: float = 1.0,
    kit_id: uuid.UUID | None = None,
    reason: str | None = None,
    symptom_reason: str | None = None,
    notes: str | None = None,
    taken_at: str | None = None,
) -> MedIntake:
    """Ситуативный приём лекарства по требованию (PRN, as-needed) (ADR-207)."""
    actual_reason = reason or symptom_reason
    parts = []
    if actual_reason and actual_reason.strip():
        parts.append(f"Симптом / повод: {actual_reason.strip()}")
    if notes and notes.strip():
        parts.append(notes.strip())
    reason_note = " | ".join(parts) if parts else None
    return await record_intake(
        db,
        user_id=user_id,
        medication_id=medication_id,
        schedule_id=None,
        status="taken",
        taken_at=taken_at,
        quantity_taken=quantity_taken,
        notes=reason_note,
        kit_id=kit_id,
        is_prn=True,
        deduct_stock=True,
        gamification=True,
    )


async def delete_intake(
    db: AsyncSession,
    user_id: uuid.UUID,
    intake_id: uuid.UUID,
    *,
    restore_stock: bool = True,
) -> bool:
    """Отмена / удаление факта приёма с возвратом списанного остатка в MedStock (ADR-207)."""
    stmt = select(MedIntake).where(MedIntake.id == intake_id, MedIntake.user_id == user_id)
    it = (await db.execute(stmt)).scalar_one_or_none()
    if not it:
        return False

    if restore_stock and it.status == "taken" and it.stock_id and it.quantity_taken and it.quantity_taken > 0:
        st = (
            await db.execute(select(MedStock).where(MedStock.id == it.stock_id, MedStock.user_id == user_id))
        ).scalar_one_or_none()
        if st:
            st.quantity = round(st.quantity + it.quantity_taken, 4)
            db.add(st)

    await db.delete(it)
    await db.flush()
    return True

