"""Serialization helpers: model → dict."""

from __future__ import annotations

from datetime import datetime

from app.models.medication import Medication, MedSchedule, MedStock


def composition_rows(m: Medication) -> list[dict]:
    """Компоненты препарата в порядке sort_order."""
    try:
        from sqlalchemy import inspect
        insp = inspect(m)
        if hasattr(insp, "unloaded") and "components" in insp.unloaded:
            return []
    except Exception:
        pass

    rows = []
    for c in sorted(m.components or [], key=lambda x: (x.sort_order or 0, x.created_at or datetime.min)):
        rows.append(
            {
                "substance": c.substance.name if c.substance else "",
                "inn": c.substance.inn if c.substance else None,
                "amount": float(c.amount) if c.amount is not None else None,
                "unit": c.unit,
                "variant": c.variant.name if c.variant else None,
            }
        )
    return rows


def composition_label(m: Medication) -> str:
    """Короткая подпись состава: «Эстрадиол 2 мг + Дидрогестерон 10 мг»."""
    rows = composition_rows(m)
    if not rows:
        return ""
    parts: list[str] = []
    for r in rows:
        amount = f"{r['amount']:g}" if r["amount"] is not None else ""
        unit = r["unit"] or ""
        dose = f" {amount} {unit}".rstrip() if (amount or unit) else ""
        label = f"{r['substance']}{dose}"
        if r["variant"] and len({x["variant"] for x in rows}) > 1:
            label += f" ({r['variant']})"
        parts.append(label)
    return " + ".join(parts)


def med_dict(m: Medication) -> dict:
    from app.services.med.substances import extract_med_substances

    return {
        "id": str(m.id),
        "name": m.name,
        "kind": m.kind,
        "active_ingredient": m.active_ingredient,
        "analogues": m.analogues,
        "form": m.form,
        "strength": m.strength,
        "manufacturer": m.manufacturer,
        "prescription_required": m.prescription_required,
        "storage_conditions": m.storage_conditions,
        "unit": m.unit,
        "instructions": m.instructions,
        "notes": m.notes,
        "allow_ul_override": m.allow_ul_override,
        "components": composition_rows(m),
        "composition_label": composition_label(m),
        "available_substances": extract_med_substances(m),
        "is_active": m.is_active,
    }


def stock_dict(st: MedStock) -> dict:
    return {
        "id": str(st.id),
        "medication_id": str(st.medication_id),
        "medication_name": st.medication.name if st.medication else "",
        "kit_id": str(st.kit_id) if st.kit_id else None,
        "kit_name": st.kit.name if st.kit else None,
        "quantity": st.quantity,
        "unit": st.unit,
        "lot_number": st.lot_number,
        "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
        "low_stock_threshold": st.low_stock_threshold,
    }


def schedule_dict(s: MedSchedule) -> dict:
    return {
        "id": str(s.id),
        "medication_id": str(s.medication_id),
        "medication_name": s.medication.name if s.medication else "",
        "dose_quantity": s.dose_quantity,
        "dose_unit": s.dose_unit,
        "frequency_type": s.frequency_type,
        "times_per_day": s.times_per_day,
        "times_of_day": s.times_of_day,
        "interval_hours": s.interval_hours,
        "days_of_week": s.days_of_week,
        "start_date": s.start_date.isoformat() if s.start_date else None,
        "end_date": s.end_date.isoformat() if s.end_date else None,
        "food_relation": s.food_relation,
        "duration_days": s.duration_days,
        "meal_timing": s.meal_timing,
        "meal_offset_min": s.meal_offset_min,
        "instructions": s.instructions,
        "is_active": s.is_active,
    }
