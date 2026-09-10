"""Unit conversion, daily limits, variant-for-day, equivalents (ADR-190 F/G)."""

from __future__ import annotations

import re
from datetime import date

from app.models.medication import (
    MedComponent,
    Medication,
    MedSchedule,
    MedStock,
    MedVariant,
)
from app.timeutils import local_today

# ─────────────────────────────────────────────────────────────────────────────
# Unit conversion
# ─────────────────────────────────────────────────────────────────────────────

UNIT_TO_MG: dict[str, float] = {"мкг": 0.001, "мг": 1.0, "г": 1000.0}
ME_TO_MCG: dict[str, float] = {"колекальциферол": 40.0, "colecalciferol": 40.0}


def _norm_unit(unit: str | None) -> str:
    return (unit or "").strip().lower()


def to_mg(amount: float | None, unit: str | None) -> float | None:
    """Количество в мг (для единиц мкг/мг/г); иное (МЕ/мл/…) → None."""
    if amount is None:
        return None
    factor = UNIT_TO_MG.get(_norm_unit(unit))
    return amount * factor if factor is not None else None


def _convert_unit(value: float, unit: str | None, substance_key: str, target_unit: str | None) -> float | None:
    """Пересчёт value из unit в target_unit (мкг/мг/г и МЕ↔мкг для известных веществ)."""
    u, t = _norm_unit(unit), _norm_unit(target_unit)
    if u == t or not t:
        return value
    if u in UNIT_TO_MG and t in UNIT_TO_MG:
        return value * UNIT_TO_MG[u] / UNIT_TO_MG[t]
    factor = ME_TO_MCG.get(substance_key)
    if factor is None:
        return None
    if u == "ме" and t == "мкг":
        return value / factor
    if u == "мкг" and t == "ме":
        return value * factor
    return None


def _norm_form(form: str | None) -> str:
    return re.sub(r"\s+", " ", (form or "").strip().lower())


def med_substance_keys(m: Medication) -> set[str]:
    """Набор действующих веществ препарата (norm_key) — сигнатура для замены."""
    return {c.substance.norm_key for c in m.components or [] if c.substance and c.substance.norm_key}


def med_substance_mg_map(m: Medication) -> dict[str, float]:
    """norm_key → мг на единицу формы (максимум по компонентам; пересчёт доз в мг)."""
    out: dict[str, float] = {}
    for c in m.components or []:
        if not c.substance or not c.substance.norm_key:
            continue
        mg = to_mg(c.amount, c.unit)
        if mg is not None:
            out[c.substance.norm_key] = max(out.get(c.substance.norm_key, 0.0), mg)
    return out


def variant_for_day(m: Medication, sched: MedSchedule | None, day: date) -> MedVariant | None:
    """Вариант пачки, активный в день day (ADR-190, фаза G)."""
    vs = sorted(m.variants or [], key=lambda v: v.sort_order or 0)
    if not vs:
        return None
    if len(vs) == 1:
        return vs[0]
    lengths = [max(1, v.count_per_pack or 1) for v in vs]
    total = sum(lengths)
    start = sched.start_date if sched else None
    if start is None:
        return vs[0]
    pos = (day - start).days
    if pos < 0:
        return vs[0]
    pos %= total
    for v, ln in zip(vs, lengths, strict=False):
        if pos < ln:
            return v
        pos -= ln
    return vs[0]


def day_components(m: Medication, sched: MedSchedule | None, day: date) -> list[MedComponent]:
    """Компоненты препарата, релевантные для дня (с учётом варианта пачки)."""
    v = variant_for_day(m, sched, day)
    if not (m.variants or []):
        return list(m.components or [])
    return [c for c in m.components or [] if c.variant_id is None or (v is not None and c.variant_id == v.id)]


def _stock_available(stocks: list[MedStock], today: date | None = None) -> float:
    """Сумма остатков по неистёкшим партиям."""
    today = today or local_today()
    return round(sum(float(st.quantity or 0) for st in stocks if st.expiry_date is None or st.expiry_date >= today), 3)


def equivalent_candidates(
    source: Medication,
    meds: list[Medication],
    stocks_by_med: dict[str, list[MedStock]],
) -> list[dict]:
    """Кандидаты-заменители по составу (ADR-190, фаза F)."""
    from app.services.med.serializers import composition_label

    src_keys = med_substance_keys(source)
    if not src_keys:
        return []
    src_mg = med_substance_mg_map(source)
    src_form = _norm_form(source.form)
    src_strength = re.sub(r"\s+", " ", (source.strength or "").strip().lower())
    out: list[dict] = []
    for cand in meds:
        if cand.id == source.id or not cand.is_active or cand.kind != source.kind:
            continue
        stocks = stocks_by_med.get(str(cand.id), [])
        if _stock_available(stocks) <= 0:
            continue
        keys = med_substance_keys(cand)
        if not (keys & src_keys):
            continue
        full = keys == src_keys
        form_eq = bool(src_form) and src_form == _norm_form(cand.form)
        cand_mg = med_substance_mg_map(cand)
        cand_strength = re.sub(r"\s+", " ", (cand.strength or "").strip().lower())
        shared = [k for k in src_keys if k in src_mg and k in cand_mg]
        match = "offer"
        ratio: float | None = None
        if full and (form_eq or not src_form):
            if shared:
                ratios = [src_mg[k] / cand_mg[k] for k in shared if cand_mg[k]]
                if ratios and all(abs(r - ratios[0]) < 1e-6 for r in ratios):
                    match = "auto"
                    ratio = ratios[0]
            if match == "offer" and (
                (src_strength and src_strength == cand_strength) or (not src_strength and not cand_strength)
            ):
                match = "auto"
        stock_rows = []
        for st in stocks:
            if st.expiry_date is not None and st.expiry_date < local_today():
                continue
            stock_rows.append(
                {
                    "id": str(st.id),
                    "quantity": float(st.quantity or 0),
                    "unit": st.unit,
                    "kit_name": st.kit.name if st.kit else None,
                    "location": kit_location_label(st.kit) if st.kit else "",
                    "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
                }
            )
        out.append(
            {
                "medication_id": str(cand.id),
                "name": cand.name,
                "form": cand.form,
                "strength": cand.strength,
                "manufacturer": cand.manufacturer,
                "composition_label": composition_label(cand),
                "match": match,
                "qty_ratio_per_unit": round(ratio, 4) if ratio is not None else None,
                "stock_total": _stock_available(stocks),
                "stock_rows": stock_rows,
            }
        )
    out.sort(key=lambda x: (0 if x["match"] == "auto" else 1, (x["name"] or "").lower()))
    return out


def daily_limit_exceedances(
    meds: list[Medication],
    schedules: list[MedSchedule],
    stocks: list[MedStock],
    day: date | None = None,
) -> dict:
    """Сверка планируемого на день приёма с суточными пределами веществ (ADR-190, фаза G)."""
    from app.services.med.regimen import doses_today

    today = day or local_today()
    med_by_id = {str(m.id): m for m in meds}
    accum: dict[str, dict] = {}
    for s in schedules:
        if doses_today(s, today) <= 0:
            continue
        m = med_by_id.get(str(s.medication_id))
        if m is None:
            continue
        per_day_doses = doses_today(s, today)
        contrib_mg = per_day_doses * float(s.dose_quantity or 1.0)
        for c in day_components(m, s, today):
            sub = c.substance
            if sub is None or not sub.norm_key or sub.daily_max_amt is None:
                continue
            key = sub.norm_key
            bucket = accum.setdefault(
                key,
                {
                    "substance": sub.name,
                    "inn": sub.inn,
                    "max": float(sub.daily_max_amt),
                    "unit": sub.daily_max_unit,
                    "note": sub.daily_max_note,
                    "amount": 0.0,
                    "meds": {},
                },
            )
            if to_mg(c.amount, c.unit) is not None:
                conv = _convert_unit(to_mg(c.amount, c.unit), "мг", key, bucket["unit"]) or to_mg(c.amount, c.unit)
            else:
                conv = _convert_unit(float(c.amount or 0), c.unit, key, bucket["unit"])
                if conv is None:
                    continue
            contribution = conv * contrib_mg
            bucket["amount"] += contribution
            med_ref = bucket["meds"].setdefault(
                str(m.id), {"name": m.name, "allow_ul_override": bool(m.allow_ul_override), "amount": 0.0}
            )
            med_ref["amount"] += contribution
    warnings: list[dict] = []
    allowed: list[dict] = []
    for _key, bucket in accum.items():
        if bucket["unit"] and bucket["amount"] <= bucket["max"] + 1e-9:
            continue
        meds_list = [
            {
                "medication_id": mid,
                "name": r["name"],
                "allow_ul_override": r["allow_ul_override"],
                "amount": round(r.get("amount", 0.0), 4),
            }
            for mid, r in bucket["meds"].items()
        ]
        entry = {
            "substance": bucket["substance"],
            "inn": bucket["inn"],
            "planned": round(bucket["amount"], 4),
            "max": bucket["max"],
            "unit": bucket["unit"],
            "note": bucket["note"],
            "meds": sorted(meds_list, key=lambda x: x["name"].lower()),
        }
        if all(r["allow_ul_override"] for r in meds_list):
            allowed.append(entry)
        else:
            warnings.append(entry)
    warnings.sort(key=lambda x: -(x["planned"] - x["max"]))
    allowed.sort(key=lambda x: -(x["planned"] - x["max"]))
    return {"warnings": warnings, "allowed": allowed}


def location_path(loc) -> str:
    """Полный путь локации: 'Квартира / Спальня / Тумбочка'."""
    parts: list[str] = []
    cur = loc
    while cur is not None:
        parts.append(cur.title_ru or cur.slug)
        cur = cur.parent
    return " / ".join(reversed(parts))


def kit_location_label(kit) -> str:
    """Человекочитаемое место аптечки."""
    if kit is None:
        return ""
    if kit.location_id and kit.linked_location is not None:
        return location_path(kit.linked_location)
    return kit.location or ""
