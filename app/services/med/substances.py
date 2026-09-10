"""Substances / composition helpers (ADR-190, phase E)."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import (
    MedComponent,
    Medication,
    MedSubstance,
    MedVariant,
)

# Должен совпадать с _norm_key в миграции 097 (ADR-190 §3.1).
_NORM_STRIP_RE = re.compile(r"[^a-zа-я0-9 ]")


def normalize_substance(name: str) -> str:
    """Канонический ключ вещества: trim → lower → ё→е → знаки препинания → схлопывание пробелов."""
    s = (name or "").strip().lower().replace("ё", "е")
    s = _NORM_STRIP_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


async def find_or_create_substance(
    db: AsyncSession,
    *,
    name: str,
    inn: str | None = None,
    synonyms: list[str] | None = None,
    daily_max_amt: float | None = None,
    daily_max_unit: str | None = None,
    daily_max_note: str | None = None,
    is_custom: bool = True,
) -> MedSubstance:
    """Найти вещество по norm_key или создать (пользовательские строки)."""
    norm = normalize_substance(name)
    if not norm:
        raise ValueError("Substance name is required")
    sub = (await db.execute(select(MedSubstance).where(MedSubstance.norm_key == norm))).scalar_one_or_none()
    if sub is None:
        sub = MedSubstance(
            name=(name or "").strip()[:200],
            norm_key=norm,
            inn=(inn or "").strip()[:200] or None,
            synonyms=synonyms or None,
            daily_max_amt=daily_max_amt,
            daily_max_unit=(daily_max_unit or "").strip()[:10] or None,
            daily_max_note=(daily_max_note or "").strip()[:300] or None,
            is_custom=is_custom,
        )
        db.add(sub)
        await db.flush()
    else:
        changed = False
        if inn and not sub.inn:
            sub.inn = inn[:200]
            changed = True
        if daily_max_amt is not None and sub.daily_max_amt is None:
            sub.daily_max_amt = daily_max_amt
            sub.daily_max_unit = (daily_max_unit or "").strip()[:10] or None
            sub.daily_max_note = (daily_max_note or "").strip()[:300] or None
            changed = True
        if changed:
            db.add(sub)
            await db.flush()
    return sub


def parse_components_payload(raw) -> list[dict]:
    """Распарсить payload состава (JSON-строка формы или list JSON API) в нормализованные строки."""
    if not raw:
        return []
    if isinstance(raw, list):
        data = raw
    elif isinstance(raw, str):
        try:
            data = json.loads(raw or "[]")
        except (ValueError, TypeError):
            raise ValueError("components: invalid JSON") from None
    else:
        return []
    if not isinstance(data, list):
        raise ValueError("components must be a list")
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        sub_name = (item.get("substance") or item.get("name") or "").strip()
        if not sub_name:
            continue
        variant = (item.get("variant") or "").strip() or None
        norm = normalize_substance(sub_name)
        key = (norm, normalize_substance(variant) if variant else "")
        if key in seen:
            continue
        seen.add(key)
        amount = item.get("amount")
        if isinstance(amount, str):
            amount = amount.strip() or None
        try:
            amount = float(amount) if amount not in (None, "") else None
        except (TypeError, ValueError):
            amount = None
        rows.append(
            {
                "substance": sub_name,
                "inn": (item.get("inn") or "").strip() or None,
                "amount": amount,
                "unit": (item.get("unit") or "").strip() or None,
                "variant": variant,
                "daily_max_amt": item.get("daily_max_amt"),
                "daily_max_unit": item.get("daily_max_unit"),
                "daily_max_note": item.get("daily_max_note"),
            }
        )
    return rows


async def sync_med_components(db: AsyncSession, m: Medication, raw_components: Any = None) -> None:
    """Пересоздать состав препарата из payload (варианты пачки группируются по имени)."""
    rows = parse_components_payload(raw_components)
    await db.execute(delete(MedComponent).where(MedComponent.medication_id == m.id))
    await db.execute(delete(MedVariant).where(MedVariant.medication_id == m.id))
    variant_ids: dict[str, MedVariant] = {}
    for order, row in enumerate(rows):
        substance = await find_or_create_substance(
            db,
            name=row["substance"],
            inn=row.get("inn"),
            daily_max_amt=row.get("daily_max_amt"),
            daily_max_unit=row.get("daily_max_unit"),
            daily_max_note=row.get("daily_max_note"),
        )
        variant: MedVariant | None = None
        if row.get("variant"):
            variant = variant_ids.get(row["variant"])
            if variant is None:
                variant = MedVariant(
                    medication_id=m.id,
                    name=row["variant"][:100],
                    sort_order=len(variant_ids),
                )
                db.add(variant)
                await db.flush()
                variant_ids[row["variant"]] = variant
        db.add(
            MedComponent(
                medication_id=m.id,
                variant_id=variant.id if variant else None,
                substance_id=substance.id,
                amount=row.get("amount"),
                unit=row.get("unit"),
                sort_order=order,
            )
        )
    await db.flush()


async def get_substances(db: AsyncSession, user_id: uuid.UUID, *, limit: int = 300) -> list[dict]:
    """Справочник веществ для подсказок формы (системные + созданные пользователем)."""
    subs = (await db.execute(select(MedSubstance).order_by(MedSubstance.name).limit(limit))).scalars().all()
    return [
        {"id": str(s.id), "name": s.name, "inn": s.inn, "norm_key": s.norm_key, "is_custom": s.is_custom}
        for s in subs
    ]


def extract_med_substances(m: Medication) -> list[str]:
    """Извлекает список действующих веществ препарата из components или active_ingredient.

    Примеры:
    - components: [{'substance': 'Эстрадиол'}, {'substance': 'Дидрогестерон'}] -> ['Эстрадиол', 'Дидрогестерон']
    - active_ingredient: 'эстрадиол 2 мг + дидрогестерон 10 мг' -> ['Эстрадиол', 'Дидрогестерон']
    - active_ingredient: 'Ибупрофен, парацетамол' -> ['Ибупрофен', 'Парацетамол']
    """
    found: list[str] = []
    seen: set[str] = set()

    has_components = False
    try:
        from sqlalchemy import inspect
        insp = inspect(m)
        if hasattr(insp, "unloaded") and "components" in insp.unloaded:
            has_components = False
        else:
            has_components = bool(getattr(m, "components", None))
    except Exception:
        has_components = bool(getattr(m, "components", None))

    if has_components:
        for c in m.components:
            name = c.substance.name.strip() if c.substance and c.substance.name else ""
            if name:
                norm = normalize_substance(name)
                if norm and norm not in seen:
                    seen.add(norm)
                    found.append(name.capitalize())

    if not found and getattr(m, "active_ingredient", None):
        raw = m.active_ingredient.strip()
        cleaned = re.sub(r"\b\d+(?:[\.,]\d+)?\s*(?:мг|г|мкг|мл|mg|g|mcg|ml|ед|iu|%)\b", " ", raw, flags=re.IGNORECASE)
        parts = re.split(r"[\+;,/]|(?:\s+и\s+)|(?:\s+and\s+)", cleaned)
        for part in parts:
            p = re.sub(r"[^a-zA-Zа-яА-ЯёЁ\s\-]", " ", part).strip()
            norm = normalize_substance(p)
            if norm and len(norm) >= 3 and norm not in seen:
                seen.add(norm)
                found.append(p.capitalize())

    return found
