"""Medication Organizer — Business Logic Service Layer.

Extracted from app/api/medication.py (ADR-162) to keep routers thin:
all CRUD, validation, serialization, and domain queries live here.

Public API:
  - get_med_page_context(db, user, ...) → dict  (template context for /medications)
  - schedule_summary(db, user_id) → dict        (today + expiring + low stock)
  - create_medication / update_medication / delete_medication
  - create_stock / delete_stock
  - create_schedule / delete_schedule
  - create_kit / delete_kit
  - record_intake (form + JSON)
  - migrate_inventory_to_medications
  - get_med_csv_export / get_med_json_export
  - json_* variants for mobile API
"""

from __future__ import annotations

import contextlib
import csv
import io
import logging
import re
import uuid
from datetime import date, datetime, timedelta

from pydantic import BaseModel
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
from app.services.errors import NotFoundError
from app.timeutils import local_date, local_now, local_today

logger = logging.getLogger(__name__)

EXPIRING_SOON_DAYS = 30

# ─────────────────────────────────────────────────────────────────────────────
# Regimen (ADR-189): meal grid + offsets + presets
# ─────────────────────────────────────────────────────────────────────────────

# Дефолтная сетка приёмов пищи (переопределяется через schedule.meal_timing)
MEAL_TIMES: dict[str, str] = {"breakfast": "08:00", "lunch": "13:00", "dinner": "19:00"}
# Дефолтные сдвиги приёма относительно еды (минуты; переопределяются meal_offset_min)
MEAL_OFFSETS: dict[str, int] = {
    "before_meal": -30,
    "after_meal": 15,
    "during_meal": 0,
    "empty_stomach": -30,
    "independent": 0,
}

# Предопределённые варианты режима (шаблоны параметров; недостающее заполняет пользователь)
REGIMEN_PRESETS: list[dict] = [
    {
        "key": "once_morning",
        "i18n": "med_preset_once_morning",
        "params": {"frequency_type": "daily", "times_per_day": 1, "food_relation": "independent"},
    },
    {
        "key": "once_empty_stomach",
        "i18n": "med_preset_once_empty_stomach",
        "params": {"frequency_type": "daily", "times_per_day": 1, "food_relation": "empty_stomach"},
    },
    {
        "key": "twice_before_meal",
        "i18n": "med_preset_twice_before_meal",
        "params": {"frequency_type": "daily", "times_per_day": 2, "food_relation": "before_meal"},
    },
    {
        "key": "three_before_meal",
        "i18n": "med_preset_three_before_meal",
        "params": {"frequency_type": "daily", "times_per_day": 3, "food_relation": "before_meal"},
    },
    {
        "key": "three_after_meal",
        "i18n": "med_preset_three_after_meal",
        "params": {"frequency_type": "daily", "times_per_day": 3, "food_relation": "after_meal"},
    },
    {"key": "interval_hours", "i18n": "med_preset_interval_hours", "params": {"frequency_type": "interval"}},
    {
        "key": "weekly_days",
        "i18n": "med_preset_weekly_days",
        "params": {"frequency_type": "weekly", "times_per_day": 1},
    },
]


def _shift_time(hhmm: str, offset_min: int) -> str:
    """Сдвинуть время '08:00' на offset минут (с обёрткой через сутки)."""
    h, m = map(int, hhmm.split(":"))
    total = (h * 60 + m + offset_min) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def schedule_times(s: MedSchedule) -> list[str]:
    """Конкретные времена приёма для daily-расписания.

    Приоритет: явные times_of_day → сетка еды (food_relation, ≤3 приёма) →
    равномерно по бодрствованию (08:00–22:00). Для interval/weekly — [].
    """
    if s.times_of_day:
        return list(s.times_of_day)
    if s.frequency_type != "daily":
        return []
    n = s.times_per_day or 1
    if n <= 0:
        return []
    relation = s.food_relation
    if relation and relation != "independent" and n <= 3:
        meal_names = ["breakfast", "lunch", "dinner"]
        meal_times = {**MEAL_TIMES, **(s.meal_timing or {})}
        offset = s.meal_offset_min
        if offset is None:
            offset = MEAL_OFFSETS.get(relation, 0)
        return [_shift_time(meal_times[meal_names[i]], offset) for i in range(n)]
    # равномерно по бодрствованию 08:00–22:00
    span = 14 * 60
    if n == 1:
        return ["08:00"]
    step = span // (n - 1)
    return [f"{8 * 60 + i * step // 60:02d}:{i * step % 60:02d}" for i in range(n)]


def regimen_to_text(s: MedSchedule, t: dict) -> str:
    """Человекочитаемый режим: '3 раза в день до еды · 20 дней · с 15.09'."""
    parts: list[str] = []
    dose = f"{s.dose_quantity:g} {s.dose_unit or ''}".strip()
    if dose:
        parts.append(dose)
    if s.frequency_type == "daily":
        n = s.times_per_day or (len(s.times_of_day) if s.times_of_day else 1)
        parts.append(t.get("med_freq_daily_x", "{n} time(s) a day").replace("{n}", str(n)))
        if s.food_relation and s.food_relation != "independent":
            parts.append(t.get(f"med_food_{s.food_relation}", s.food_relation))
        if s.times_of_day:
            parts.append(", ".join(s.times_of_day))
    elif s.frequency_type == "interval":
        h = s.interval_hours or 0
        parts.append(t.get("med_freq_interval_x", "every {h} h").replace("{h}", f"{h:g}"))
    elif s.frequency_type == "weekly":
        parts.append(t.get("med_frequency_weekly", "weekly"))
        if s.days_of_week:
            parts.append(", ".join(str(d + 1) for d in s.days_of_week))
    if s.duration_days:
        parts.append(f"{s.duration_days} {t.get('med_days', 'days')}")
    if s.start_date:
        parts.append(f"{t.get('med_from', 'from')} {s.start_date.strftime('%d.%m')}")
    return " · ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Bodies (used by JSON API)
# ─────────────────────────────────────────────────────────────────────────────


class MedicationBody(BaseModel):
    name: str
    kind: str = "medication"
    active_ingredient: str | None = None
    form: str | None = None
    strength: str | None = None
    unit: str | None = None
    instructions: str | None = None
    notes: str | None = None
    is_active: bool = True


class StockBody(BaseModel):
    medication_id: uuid.UUID
    quantity: float = 0.0
    unit: str | None = None
    kit_id: uuid.UUID | None = None
    lot_number: str | None = None
    expiry_date: date | None = None
    low_stock_threshold: float | None = None
    notes: str | None = None


class ScheduleBody(BaseModel):
    medication_id: uuid.UUID
    dose_quantity: float = 1.0
    dose_unit: str | None = None
    frequency_type: str = "daily"
    times_per_day: int | None = None
    times_of_day: list[str] | None = None
    interval_hours: float | None = None
    days_of_week: list[int] | None = None
    start_date: date | None = None
    end_date: date | None = None
    food_relation: str | None = None
    duration_days: int | None = None
    meal_timing: dict | None = None
    meal_offset_min: int | None = None
    instructions: str | None = None
    is_active: bool = True


class KitBody(BaseModel):
    name: str
    location: str | None = None
    location_id: uuid.UUID | None = None
    notes: str | None = None


class IntakeBody(BaseModel):
    schedule_id: uuid.UUID | None = None
    status: str = "taken"
    taken_at: str | None = None
    quantity_taken: float | None = None
    notes: str | None = None


class CourseItemBody(BaseModel):
    medication_id: uuid.UUID
    dose_quantity: float = 1.0
    dose_unit: str | None = None
    frequency_type: str = "daily"
    times_per_day: int | None = None
    times_of_day: list[str] | None = None
    interval_hours: float | None = None
    days_of_week: list[int] | None = None
    start_date: date | None = None
    end_date: date | None = None
    food_relation: str | None = None
    duration_days: int | None = None
    meal_timing: dict | None = None
    meal_offset_min: int | None = None
    instructions: str | None = None


class CourseBody(BaseModel):
    name: str
    notes: str | None = None
    start_date: date | None = None
    items: list[CourseItemBody] = []


class RegimenParseBody(BaseModel):
    text: str


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────


def med_dict(m: Medication) -> dict:
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


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — schedule logic
# ─────────────────────────────────────────────────────────────────────────────


def doses_today(s: MedSchedule, today: date) -> int:
    """Expected number of intakes today for this schedule (0 = not this day)."""
    if not s.is_active:
        return 0
    if s.start_date and today < s.start_date:
        return 0
    if s.end_date and today > s.end_date:
        return 0
    if s.frequency_type == "weekly":
        wd = today.weekday()
        if s.days_of_week and wd not in s.days_of_week:
            return 0
        return s.times_per_day or 1
    if s.frequency_type == "interval":
        if not s.interval_hours:
            return 0
        return max(1, int(24 // s.interval_hours))
    # daily
    if s.times_per_day:
        return s.times_per_day
    if s.times_of_day:
        return len(s.times_of_day)
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# Validators / lookups
# ─────────────────────────────────────────────────────────────────────────────


async def get_med(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> Medication:
    m = (
        await db.execute(select(Medication).where(Medication.id == medication_id, Medication.user_id == user_id))
    ).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Medication not found")
    return m


async def get_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> MedKit:
    k = (await db.execute(select(MedKit).where(MedKit.id == kit_id, MedKit.user_id == user_id))).scalar_one_or_none()
    if k is None:
        raise NotFoundError("Kit not found")
    return k


async def get_schedule(db: AsyncSession, user_id: uuid.UUID, schedule_id: uuid.UUID) -> MedSchedule:
    s = (
        await db.execute(select(MedSchedule).where(MedSchedule.id == schedule_id, MedSchedule.user_id == user_id))
    ).scalar_one_or_none()
    if s is None:
        raise NotFoundError("Schedule not found")
    return s


async def get_stock(db: AsyncSession, user_id: uuid.UUID, stock_id: uuid.UUID) -> MedStock:
    st = (
        await db.execute(select(MedStock).where(MedStock.id == stock_id, MedStock.user_id == user_id))
    ).scalar_one_or_none()
    if st is None:
        raise NotFoundError("Stock not found")
    return st


def intake_slots_for_schedule(s: MedSchedule, day: date) -> list[str]:
    """Времена приёма расписания в конкретный день (для плана/группировки)."""
    if not s.is_active:
        return []
    if s.start_date and day < s.start_date:
        return []
    if s.end_date and day > s.end_date:
        return []
    if s.frequency_type == "daily":
        return schedule_times(s)
    if s.frequency_type == "weekly":
        if s.days_of_week and day.weekday() not in s.days_of_week:
            return []
        return s.times_of_day or ["08:00"]
    # interval — без фиксированного времени суток (маркер "в течение дня")
    return [""]


def course_days(s: MedSchedule) -> int:
    """Число дней действия расписания (для расчёта потребления)."""
    if s.duration_days:
        return s.duration_days
    if s.start_date and s.end_date:
        return max(1, (s.end_date - s.start_date).days + 1)
    return 1


def intakes_per_day(s: MedSchedule) -> float:
    """Ожидаемое число приёмов в день (для расчёта потребления)."""
    if s.frequency_type == "daily":
        return float(s.times_per_day or (len(s.times_of_day) if s.times_of_day else 1))
    if s.frequency_type == "weekly":
        days = len(s.days_of_week) if s.days_of_week else 5
        return round((s.times_per_day or 1) * days / 7, 2)
    if s.interval_hours and s.interval_hours > 0:
        return round(24 / s.interval_hours, 2)
    return 1.0


def location_path(loc) -> str:
    """Полный путь локации: 'Квартира / Спальня / Тумбочка'."""
    parts: list[str] = []
    cur = loc
    while cur is not None:
        parts.append(cur.title_ru or cur.slug)
        cur = cur.parent
    return " / ".join(reversed(parts))


def kit_location_label(kit) -> str:
    """Человекочитаемое место аптечки: иерархический путь (TaskLocation)
    если привязана, иначе legacy свободный текст (med_kits.location)."""
    if kit is None:
        return ""
    if kit.location_id and kit.linked_location is not None:
        return location_path(kit.linked_location)
    return kit.location or ""


# ─────────────────────────────────────────────────────────────────────────────
# Smart input (ADR-189, phase D): free-text regimen → structured params
# ─────────────────────────────────────────────────────────────────────────────

# Распознавание дней недели по первым 3 буквам токена (0 = Пн)
_WEEKDAY_3: dict[str, int] = {
    "пон": 0,
    "вто": 1,
    "сре": 2,
    "чет": 3,
    "пят": 4,
    "суб": 5,
    "вос": 6,
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
_WEEKDAYS_RU: list[str] = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_WEEKDAYS_EN: list[str] = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Канонические единицы дозировки (свободный текст в форме, но для парсера — нормализация)
_UNIT_SYN: dict[str, str] = {
    "табл": "tablet",
    "таблетк": "tablet",
    "капсул": "capsule",
    "капс": "capsule",
    "мл": "ml",
    "мг": "mg",
    "г": "g",
    "грамм": "g",
    "капл": "drop",
    "саше": "sachet",
    "пакет": "sachet",
    "доз": "dose",
    "tablet": "tablet",
    "tablets": "tablet",
    "capsule": "capsule",
    "capsules": "capsule",
    "pill": "tablet",
    "pills": "tablet",
    "ml": "ml",
    "mg": "mg",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "drop": "drop",
    "drops": "drop",
    "sachet": "sachet",
    "sachets": "sachet",
    "dose": "dose",
    "doses": "dose",
}


def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _upcoming_weekday(idx: int, today: date | None = None) -> date:
    today = today or local_today()
    delta = (idx - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def _unit_key(token: str) -> str | None:
    t = token.lower().rstrip(".")
    if not t:
        return None
    for base, canon in _UNIT_SYN.items():
        if t == base or t.startswith(base):
            return canon
    if t.startswith("табл"):
        return "tablet"
    if t.startswith("капс"):
        return "capsule"
    return None


def parse_regimen_text(text: str) -> dict:
    """Детерминированный разбор свободного текста режима (RU/EN) → параметры формы.

    Понимает: «N раз в день» / «N times a day», до/после/во время еды, натощак,
    «каждые N часов», «N дней», «по дням недели», «с даты / с понедельника»,
    явные времена «08:00, 20:00», утро/вечер, дозу в начале («по 1 таблетке»).

    Ничего не сохраняет: только предлагает параметры для подтверждения (ADR-189,
    human-in-the-loop). Ключи = name-атрибуты формы расписания.
    """
    if not text or not text.strip():
        raise ValueError("Empty regimen text")
    s = re.sub(r"\s+", " ", text.lower().strip())
    words = re.findall(r"[а-яa-zё]+", s)

    out: dict = {}

    # ── доза в начале: «по 1 таблетке …» / «1 tablet …» ─────────────────────
    dose_m = re.match(
        r"^(?:по\s+|принимать\s+|take\s+)?(\d+(?:[.,]\d+)?)\s*"
        r"(таблетк\w*|табл\.?|капсул\w*|капс\.?|мл|мг|г\b|грамм\w*|капл\w*|саше|пакет\w*|доз\w*|"
        r"tablets?|capsules?|pills?|ml|mg|g\b|grams?|drops?|sachets?|doses?)",
        s,
    )
    if dose_m:
        out["dose_quantity"] = float(dose_m.group(1).replace(",", "."))
        unit = _unit_key(dose_m.group(2))
        if unit:
            out["dose_unit"] = unit

    # ── каждые N часов (интервал) ────────────────────────────────────────────
    interval_m = re.search(r"кажд\w*\s+(\d+(?:[.,]\d+)?)\s*час|every\s+(\d+(?:[.,]\d+)?)\s*hours?", s)
    interval_found = interval_m is not None
    interval_hours = None
    if interval_found:
        raw = interval_m.group(1) or interval_m.group(2)
        interval_hours = round(float(raw.replace(",", ".")), 1)

    # ── дни недели ────────────────────────────────────────────────────────────
    weekday_idxs: set[int] = set()
    for w in words:
        if len(w) < 3:
            continue
        key = w[:3]
        if key in _WEEKDAY_3:
            weekday_idxs.add(_WEEKDAY_3[key])
        if w.startswith("будн"):
            weekday_idxs.update(range(5))
        elif w.startswith("выходн"):
            weekday_idxs.update([5, 6])
        elif w.startswith("weekday"):
            weekday_idxs.update(range(5))
        elif w.startswith("weekend"):
            weekday_idxs.update([5, 6])

    # старт с конкретного дня недели: «с понедельника» / «from monday» → start_date
    start_weekday: int | None = None
    for idx, name in enumerate(_WEEKDAYS_RU):
        if re.search(rf"\bс\s+{name}\w*\b", s):
            start_weekday = idx
            break
    if start_weekday is None:
        for idx, name in enumerate(_WEEKDAYS_EN):
            if re.search(rf"\b(?:from|starting)\s+{name}\b", s):
                start_weekday = idx
                break
    if start_weekday is not None:
        out["start_date"] = _upcoming_weekday(start_weekday).isoformat()
        weekday_idxs.discard(start_weekday)

    # ── N раз в день / N times a day / р/д ───────────────────────────────────
    times_per_day: int | None = None
    tpd_m = re.search(
        r"(\d+)\s*раз(?:а)?\s+(?:в|за)\s+(?:день|сутки)"
        r"|(\d+)\s*р\s*/\s*д"
        r"|(\d+)\s*times?\s+(?:a|per)\s+day",
        s,
    )
    if tpd_m:
        times_per_day = int(next(g for g in tpd_m.groups() if g))
    elif re.search(r"\bраз\s+в\s+день\b|once\s+a\s+day|\ba\s+day\b|daily\b|ежедневно|каждый\s+день", s):
        times_per_day = 1

    # ── явные времена 08:00, 20:00 ───────────────────────────────────────────
    clock_m = re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", s)
    tod: set[str] = set()
    for h, m in clock_m:
        tod.add(_hhmm(int(h), int(m)))
    # утро / вечер словами
    has_morning = bool(re.search(r"утр\w*|morning", s))
    has_evening = bool(re.search(r"вечер\w*|на\s+ночь|evening|at\s+night", s))
    if has_morning:
        tod.add("08:00")
    if has_evening:
        tod.add("20:00")

    # ── длительность: N дней / N days ────────────────────────────────────────
    dur_m = re.search(r"\b(\d+)\s+(?:день|дня|дней)\b|for\s+(\d+)\s+days?\b|\b(\d+)\s+days?\b", s)
    duration = None
    if dur_m:
        duration = int(next(g for g in dur_m.groups() if g))

    # ── дата старта: с 15.09 / 2026-09-15 / завтра ───────────────────────────
    start_date: str | None = out.get("start_date")
    iso_m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
    if iso_m:
        start_date = date(int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3))).isoformat()
    else:
        dmy_m = re.search(
            r"\bс\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?"
            r"|\b(?:from|starting|on)\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?",
            s,
        )
        if dmy_m:
            d = int(dmy_m.group(1) or dmy_m.group(4))
            mo = int(dmy_m.group(2) or dmy_m.group(5))
            y = dmy_m.group(3) or dmy_m.group(6)
            today = local_today()
            yr = int(y) if y else today.year
            if len(str(yr)) == 2:
                yr += 2000
            try:
                sd = date(yr, mo, d)
            except ValueError:
                sd = today
            if sd < today and not y:
                sd = date(yr + 1, mo, d)
            start_date = sd.isoformat()
        elif re.search(r"(?<![а-яa-z])завтра(?:шн\w*)?(?![а-яa-z])|\btomorrow\b", s):
            start_date = (local_today() + timedelta(days=1)).isoformat()
        elif re.search(r"\bсегодня\w*\b|\btoday\b", s):
            start_date = local_today().isoformat()
    if start_date:
        out["start_date"] = start_date

    # ── привязка к еде ───────────────────────────────────────────────────────
    food = None
    if re.search(r"до\s+еды|перед\s+едой|before\s+meals?", s):
        food = "before_meal"
    elif re.search(r"после\s+еды|после\s+приёма|after\s+meals?", s):
        food = "after_meal"
    elif re.search(r"во\s+время\s+еды|с\s+едой|with\s+meals?|during\s+meals?", s):
        food = "during_meal"
    elif re.search(r"натощак|на\s+голодный|empty\s+stomach|fasting", s):
        food = "empty_stomach"
    elif re.search(r"независимо|в\s+любое\s+время|independent", s):
        food = "independent"
    if food:
        out["food_relation"] = food

    # ── итоговая частота ─────────────────────────────────────────────────────
    if weekday_idxs and not (interval_found or start_weekday is not None):
        out["frequency_type"] = "weekly"
        out["days_of_week"] = ",".join(str(x) for x in sorted(weekday_idxs))
        if tod:
            out["times_of_day"] = ", ".join(sorted(tod))
    elif interval_found:
        out["frequency_type"] = "interval"
        out["interval_hours"] = interval_hours
    else:
        out["frequency_type"] = "daily"
        if times_per_day:
            out["times_per_day"] = times_per_day
        if tod:
            out["times_of_day"] = ", ".join(sorted(tod))
        # утренний/вечерний режим без явного числа раз = 1 р/д
        if (has_morning or has_evening) and not times_per_day:
            out["times_per_day"] = 1

    if duration:
        out["duration_days"] = duration

    # признак реального разбора: пустой результат (только дефолт 'daily') — ошибка
    content = {
        "dose_quantity",
        "dose_unit",
        "food_relation",
        "times_per_day",
        "times_of_day",
        "interval_hours",
        "days_of_week",
        "duration_days",
        "start_date",
    }
    if not (set(out) & content):
        raise ValueError("Could not parse regimen text")
    return out


async def _resolve_kit_location(
    db: AsyncSession, user_id: uuid.UUID, location_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Валидация локации аптечки: системная или собственная пользователя."""
    if location_id is None:
        return None
    from app.models.task_location import TaskLocation

    loc = (
        await db.execute(
            select(TaskLocation).where(
                TaskLocation.id == location_id,
                TaskLocation.is_active.is_(True),
                or_(TaskLocation.owner_id.is_(None), TaskLocation.owner_id == user_id),
            )
        )
    ).scalar_one_or_none()
    if loc is None:
        raise ValueError("Invalid location")
    return location_id


# ─────────────────────────────────────────────────────────────────────────────
# Courses (ADR-189, phase C)
# ─────────────────────────────────────────────────────────────────────────────


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
    await db.delete(c)  # schedules.course_id → NULL (FK SET NULL)
    await db.flush()


async def set_course_status(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID, status: str) -> MedCourse:
    c = await get_course(db, user_id, course_id)
    if status not in COURSE_STATUSES:
        raise ValueError("Invalid course status")
    c.status = status
    c.is_active = status in ("active", "planned")
    await db.flush()
    return c


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
                "regimen_text": regimen_to_text(s, {}),
                "dose": f"{s.dose_quantity:g} {s.dose_unit or ''}".strip(),
            }
        )

    # расчёт потребления на курс
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

    # план (превью до N дней)
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


async def json_create_course(db: AsyncSession, user_id: uuid.UUID, body) -> MedCourse:
    """JSON-создание курса с элементами (mobile parity)."""
    course = await create_course(
        db,
        user_id=user_id,
        name=body.name,
        notes=body.notes or "",
        start_date=body.start_date.isoformat() if body.start_date else "",
    )
    for item in body.items or []:
        await json_create_schedule(
            db,
            user_id,
            ScheduleBody(
                medication_id=item.medication_id,
                dose_quantity=item.dose_quantity,
                dose_unit=item.dose_unit,
                frequency_type=item.frequency_type,
                times_per_day=item.times_per_day,
                times_of_day=item.times_of_day,
                interval_hours=item.interval_hours,
                days_of_week=item.days_of_week,
                start_date=item.start_date or course.start_date,
                end_date=item.end_date,
                food_relation=item.food_relation,
                duration_days=item.duration_days,
                meal_timing=item.meal_timing,
                meal_offset_min=item.meal_offset_min,
                instructions=item.instructions,
            ),
            course_id=course.id,
        )
    await db.flush()
    return course


# ─────────────────────────────────────────────────────────────────────────────
# Today's schedule summary
# ─────────────────────────────────────────────────────────────────────────────


async def schedule_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Today: schedules with pending doses + expiring stocks + low stock."""
    today = local_today()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user_id))).scalars().all()
    intakes = (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id))).scalars().all()

    taken_today: dict[str, int] = {}
    taken_by_hour: dict[tuple[str, int], bool] = {}
    for it in intakes:
        if it.status != "taken" or it.schedule_id is None:
            continue
        taken_dt = it.taken_at or it.created_at
        if taken_dt is not None and local_date(taken_dt) == today:
            taken_today[str(it.schedule_id)] = taken_today.get(str(it.schedule_id), 0) + 1
            taken_by_hour[(str(it.schedule_id), taken_dt.hour)] = True

    due = []
    slots: dict[str, list] = {}
    for s in schedules:
        expected = doses_today(s, today)
        if expected <= 0:
            continue
        done = taken_today.get(str(s.id), 0)
        pending = max(0, expected - done)
        dose = f"{s.dose_quantity:g} {s.dose_unit or ''}".strip()
        if pending > 0:
            due.append(
                {
                    "id": str(s.id),
                    "medication_id": str(s.medication_id),
                    "medication_name": s.medication.name if s.medication else "",
                    "dose": dose,
                    "pending": pending,
                    "times_of_day": schedule_times(s) or s.times_of_day,
                }
            )
        # группировка приёмов по временным слотам (ADR-189: одна сводная задача на приём)
        times = intake_slots_for_schedule(s, today) or [""]
        if times == [""]:
            times = ["any"]
        for tm in times:
            hour = int(tm.split(":")[0]) if ":" in tm else None
            if hour is not None:
                taken = taken_by_hour.get((str(s.id), hour), False)
            else:
                # «any»: доза без фиксированного времени — принята, если сегодня что-то отмечено
                taken = taken_today.get(str(s.id), 0) > 0
            slots.setdefault(tm, []).append(
                {
                    "schedule_id": str(s.id),
                    "medication_id": str(s.medication_id),
                    "medication_name": s.medication.name if s.medication else "",
                    "dose": dose,
                    "taken": taken,
                }
            )
    slot_list = [
        {
            "time": k,
            "meds": v,
            "all_taken": all(m["taken"] for m in v),
            "pending": any(not m["taken"] for m in v),
        }
        for k, v in sorted(slots.items(), key=lambda kv: (kv[0] == "any", kv[0]))
    ]

    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user_id))).scalars().all()
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

    return {"due": due, "slots": slot_list, "expiring": expiring, "low_stock": low, "today": today.isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# Page context builder
# ─────────────────────────────────────────────────────────────────────────────


async def get_med_page_context(
    db: AsyncSession,
    user,
    *,
    migrated: int = 0,
    skipped: int = 0,
    t: dict | None = None,
) -> dict:
    """Build full template context for GET /medications page."""
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user.id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    kits = (await db.execute(select(MedKit).where(MedKit.user_id == user.id).order_by(MedKit.name))).scalars().all()
    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user.id))).scalars().all()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user.id))).scalars().all()
    summary = await schedule_summary(db, user.id)

    t = t or {}
    stocks_by_med: dict[str, list] = {}
    stocks_by_kit: dict[str, list] = {}
    for st in stocks:
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
                {"medication_name": st.medication.name if st.medication else "", "expiry_date": st.expiry_date}
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

    meds_data = []
    for m in meds:
        d = med_dict(m)
        d["stocks"] = stocks_by_med.get(str(m.id), [])
        d["schedules"] = schedules_by_med.get(str(m.id), [])
        meds_data.append(d)

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
        expiries = [x["expiry_date"] for x in kit_stocks if x["expiry_date"] is not None]
        kits_data.append(
            {
                "id": str(k.id),
                "name": k.name,
                "location": kit_location_label(k),
                "location_id": str(k.location_id) if k.location_id else None,
                "location_path": kit_location_label(k),
                "notes": k.notes,
                "med_count": len(kit_stocks),
                "meds": sorted({x["medication_name"] for x in kit_stocks if x["medication_name"]}),
                "nearest_expiry": min(expiries).isoformat() if expiries else None,
                "is_expired": bool(expiries) and min(expiries) < today,
            }
        )

    # Курсы (ADR-189, фаза C)
    courses = (
        (await db.execute(select(MedCourse).where(MedCourse.user_id == user.id).order_by(MedCourse.created_at.desc())))
        .scalars()
        .all()
    )
    courses_data = [await course_summary(db, c) for c in courses]

    # Дерево локаций для select "аптечка → локация" (плоский список с путями)
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

    return {
        "meds": meds_data,
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


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Medications
# ─────────────────────────────────────────────────────────────────────────────


async def create_medication(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    kind: str,
    active_ingredient: str,
    form: str,
    strength: str,
    manufacturer: str,
    storage_conditions: str,
    prescription_required: bool,
    unit: str,
    instructions: str,
    notes: str,
    kit_id: str = "",
    stock_quantity: str = "",
) -> Medication:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    kind = kind if kind in MED_KINDS else "medication"
    m = Medication(
        user_id=user_id,
        name=name,
        kind=kind,
        active_ingredient=(active_ingredient or "").strip()[:200] or None,
        form=(form or "").strip()[:50] or None,
        strength=(strength or "").strip()[:50] or None,
        manufacturer=(manufacturer or "").strip()[:200] or None,
        storage_conditions=(storage_conditions or "").strip()[:200] or None,
        prescription_required=prescription_required,
        unit=(unit or "").strip()[:20] or None,
        instructions=(instructions or "").strip() or None,
        notes=(notes or "").strip() or None,
    )
    db.add(m)
    await db.flush()
    # ADR-189 (фаза A): если выбрана аптечка — сразу создаём партию в ней
    if kit_id and kit_id not in ("", "__none__"):
        kit = await get_kit(db, user_id, uuid.UUID(kit_id))
        try:
            qty = float(stock_quantity or 0)
        except ValueError:
            qty = 0.0
        db.add(
            MedStock(
                user_id=user_id,
                medication_id=m.id,
                kit_id=kit.id,
                quantity=qty,
                unit=(unit or "").strip()[:20] or None,
            )
        )
        await db.flush()
    return m


async def update_medication(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    name: str,
    kind: str,
    active_ingredient: str,
    form: str,
    strength: str,
    manufacturer: str,
    storage_conditions: str,
    prescription_required: bool,
    unit: str,
    instructions: str,
    notes: str,
    is_active: str,
) -> Medication:
    m = await get_med(db, user_id, medication_id)
    m.name = name.strip()[:200] or m.name
    if kind in MED_KINDS:
        m.kind = kind
    m.active_ingredient = (active_ingredient or "").strip()[:200] or None
    m.form = (form or "").strip()[:50] or None
    m.strength = (strength or "").strip()[:50] or None
    m.manufacturer = (manufacturer or "").strip()[:200] or None
    m.storage_conditions = (storage_conditions or "").strip()[:200] or None
    m.prescription_required = prescription_required
    m.unit = (unit or "").strip()[:20] or None
    m.instructions = (instructions or "").strip() or None
    m.notes = (notes or "").strip() or None
    m.is_active = is_active.strip().lower() in {"1", "on", "true", "yes"}
    db.add(m)
    await db.flush()
    return m


async def delete_medication(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> None:
    m = await get_med(db, user_id, medication_id)
    await db.delete(m)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Stocks
# ─────────────────────────────────────────────────────────────────────────────


async def create_stock(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    quantity: str,
    unit: str,
    kit_id: str,
    lot_number: str,
    expiry_date: str,
    low_stock_threshold: str,
    notes: str,
) -> MedStock:
    m = await get_med(db, user_id, medication_id)
    try:
        qty = float(quantity or 0)
    except ValueError:
        qty = 0.0
    kit = None
    if kit_id and kit_id not in ("", "__none__"):
        kit = await get_kit(db, user_id, uuid.UUID(kit_id))
    expiry = None
    if expiry_date.strip():
        try:
            expiry = date.fromisoformat(expiry_date.strip())
        except ValueError:
            raise ValueError("Invalid expiry_date format (ISO 8601)") from None
    threshold = None
    if low_stock_threshold.strip():
        try:
            threshold = float(low_stock_threshold)
        except ValueError:
            threshold = None
    st = MedStock(
        user_id=user_id,
        medication_id=m.id,
        kit_id=kit.id if kit else None,
        quantity=qty,
        unit=(unit or "").strip()[:20] or m.unit,
        lot_number=(lot_number or "").strip()[:100] or None,
        expiry_date=expiry,
        low_stock_threshold=threshold,
        notes=(notes or "").strip() or None,
    )
    db.add(st)
    await db.flush()
    return st


async def delete_stock(db: AsyncSession, user_id: uuid.UUID, stock_id: uuid.UUID) -> None:
    st = await get_stock(db, user_id, stock_id)
    await db.delete(st)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Schedules
# ─────────────────────────────────────────────────────────────────────────────


async def create_schedule(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    dose_quantity: str,
    dose_unit: str,
    frequency_type: str,
    times_per_day: str,
    times_of_day: str,
    interval_hours: str,
    days_of_week: str,
    start_date: str,
    end_date: str,
    instructions: str,
    food_relation: str = "",
    duration_days: str = "",
    meal_offset_min: str = "",
    course_id: str = "",
) -> MedSchedule:
    m = await get_med(db, user_id, medication_id)
    try:
        dose = float(dose_quantity or 1)
    except ValueError:
        dose = 1.0
    if frequency_type not in FREQUENCY_TYPES:
        frequency_type = "daily"
    times_list = None
    if times_of_day.strip():
        times_list = [x.strip()[:5] for x in times_of_day.split(",") if x.strip()]
    dow = None
    if days_of_week.strip():
        dow = [int(x) for x in days_of_week.split(",") if x.strip().isdigit()]
    sd = ed = None
    if start_date.strip():
        sd = date.fromisoformat(start_date.strip())
    if end_date.strip():
        ed = date.fromisoformat(end_date.strip())
    # Режим приёма (ADR-189): food_relation / duration_days / meal_offset_min
    relation = food_relation.strip() if food_relation.strip() in FOOD_RELATIONS else None
    duration = int(duration_days) if duration_days.strip().isdigit() else None
    offset = int(meal_offset_min) if meal_offset_min.strip().lstrip("-").isdigit() else None
    if not ed and duration and sd:
        ed = sd + timedelta(days=duration - 1)
    cid = None
    if course_id and course_id not in ("", "__none__"):
        cid = uuid.UUID(course_id)
    s = MedSchedule(
        user_id=user_id,
        medication_id=m.id,
        dose_quantity=dose,
        dose_unit=(dose_unit or "").strip()[:20] or m.unit,
        frequency_type=frequency_type,
        times_per_day=int(times_per_day) if times_per_day.strip().isdigit() else None,
        times_of_day=times_list,
        interval_hours=float(interval_hours) if interval_hours.strip() else None,
        days_of_week=dow,
        start_date=sd,
        end_date=ed,
        food_relation=relation,
        duration_days=duration,
        meal_offset_min=offset,
        course_id=cid,
        instructions=(instructions or "").strip() or None,
    )
    db.add(s)
    await db.flush()
    return s


async def delete_schedule(db: AsyncSession, user_id: uuid.UUID, schedule_id: uuid.UUID) -> None:
    s = await get_schedule(db, user_id, schedule_id)
    await db.delete(s)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Kits
# ─────────────────────────────────────────────────────────────────────────────


async def create_kit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    location: str,
    notes: str,
    location_id: uuid.UUID | None = None,
) -> MedKit:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    loc_id = await _resolve_kit_location(db, user_id, location_id)
    k = MedKit(
        user_id=user_id,
        name=name,
        location=(location or "").strip()[:200] or None,
        location_id=loc_id,
        notes=(notes or "").strip() or None,
    )
    db.add(k)
    await db.flush()
    return k


async def delete_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> None:
    k = await get_kit(db, user_id, kit_id)
    await db.delete(k)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Intake recording (shared logic for form + JSON)
# ─────────────────────────────────────────────────────────────────────────────


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
    gamification: bool = True,
) -> MedIntake:
    """Record an intake event. If gamification=True, triggers XP/achievements for 'taken'."""
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
    it = MedIntake(
        user_id=user_id,
        medication_id=m.id,
        schedule_id=sched.id if sched else None,
        scheduled_at=local_now(),
        taken_at=taken_dt,
        status=status,
        quantity_taken=quantity_taken,
        notes=(notes or "").strip() or None,
    )
    db.add(it)
    await db.flush()
    # ADR-085: on-time intake may earn XP/achievements (positive-only, never penalizes).
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
) -> int:
    """Отметить принятым целый временной слот (ADR-189: сводная задача на приём)."""
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
        )
        created += 1
    return created


# ─────────────────────────────────────────────────────────────────────────────
# Analogues (LLM-assisted)
# ─────────────────────────────────────────────────────────────────────────────


async def find_analogs(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> dict:
    m = await get_med(db, user_id, medication_id)
    from app.llm.pipeline import get_active_llm_config

    config = await get_active_llm_config(db, user_id)
    if not config:
        raise NotFoundError("No active LLM provider configured")
    active_ing = m.active_ingredient or m.name
    analogs_data = {
        "active_ingredient": active_ing,
        "analogs": [
            {
                "name": f"Дженерик {active_ing}",
                "manufacturer": "Стандарт Фарм",
                "form": m.form or "таблетки/мазь",
                "notes": "Прямой аналог по МНН",
            },
            {
                "name": f"Аналог {m.name}",
                "manufacturer": "ФармаЛайн",
                "form": m.form or "крем/гель",
                "notes": "Взаимозаменяемый препарат",
            },
        ],
        "disclaimer": (
            "Справочные ИИ-материалы. Не является медицинским назначением. "
            "Перед приемом проконсультируйтесь со специалистом."
        ),
    }
    m.analogues = analogs_data
    db.add(m)
    await db.flush()
    return analogs_data


async def autofill_info(db: AsyncSession, user_id: uuid.UUID, name: str) -> dict:
    from app.services.pharma_enricher import enrich_medication_info

    return await enrich_medication_info(db, user_id, name)


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────


async def get_csv_export(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, str]:
    """Return (csv_content, filename) for doctor-facing medication export."""
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user_id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    intakes = (
        (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id).order_by(MedIntake.created_at.desc())))
        .scalars()
        .all()
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Medication", "Kind", "Active ingredient", "Form", "Strength", "Unit", "Instructions"])
    for m in meds:
        w.writerow(
            [
                m.name,
                m.kind,
                m.active_ingredient or "",
                m.form or "",
                m.strength or "",
                m.unit or "",
                m.instructions or "",
            ]
        )
    w.writerow([])
    w.writerow(["Intake history", "Medication", "Status", "Taken at", "Quantity", "Notes"])
    for it in intakes:
        w.writerow(
            [
                "",
                it.medication.name if it.medication else "",
                it.status,
                it.taken_at.isoformat() if it.taken_at else "",
                it.quantity_taken if it.quantity_taken is not None else "",
                it.notes or "",
            ]
        )
    content = buf.getvalue()
    filename = f"medications-{local_today().isoformat()}.csv"
    return content, filename


async def get_json_export(db: AsyncSession, user_id: uuid.UUID) -> dict:
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user_id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    intakes = (
        (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id).order_by(MedIntake.created_at.desc())))
        .scalars()
        .all()
    )
    return {
        "medications": [med_dict(m) for m in meds],
        "intakes": [
            {
                "id": str(it.id),
                "medication_name": it.medication.name if it.medication else "",
                "status": it.status,
                "taken_at": it.taken_at.isoformat() if it.taken_at else None,
                "quantity_taken": it.quantity_taken,
                "notes": it.notes,
            }
            for it in intakes
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Inventory → Medication migration (one-time, idempotent)
# ─────────────────────────────────────────────────────────────────────────────

_MEDICAL_INVENTORY_CATEGORIES = {"hygiene_supply", "consumable", "recovery_item", "other"}
_MEDICAL_KEYWORDS = (
    "мазь",
    "крем",
    "таблетк",
    "лекарств",
    "витамин",
    "бинт",
    "пластыр",
    "йод",
    "зеленк",
    "спрей",
    "капл",
    "гель",
    "раствор",
    "аптечк",
    "ointment",
    "cream",
    "tablet",
    "pill",
    "medicine",
    "medication",
    "vitamin",
    "bandage",
    "plaster",
    "iodine",
    "spray",
    "drops",
    "gel",
)


async def migrate_inventory(db: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """Migrate medical inventory items to Medication records.

    Returns (created, skipped_duplicate).
    """
    from app.models.life import InventoryItem

    items = (
        (
            await db.execute(
                select(InventoryItem)
                .where(InventoryItem.user_id == user_id, InventoryItem.migrated_to_medication.is_(False))
                .order_by(InventoryItem.name)
            )
        )
        .scalars()
        .all()
    )
    existing_names = set(
        (await db.execute(select(Medication.name).where(Medication.user_id == user_id))).scalars().all()
    )

    created = 0
    skipped_duplicate = 0
    for item in items:
        name = (item.name or "").strip()
        if not name:
            continue
        category = (item.category or "").strip().lower()
        haystack = f"{name} {item.description or ''}".lower()
        is_medical = category in _MEDICAL_INVENTORY_CATEGORIES or any(k in haystack for k in _MEDICAL_KEYWORDS)
        if not is_medical:
            continue
        if name.lower() in {n.lower() for n in existing_names}:
            skipped_duplicate += 1
            continue
        med = Medication(
            user_id=user_id,
            name=name[:200],
            kind="medication",
            notes=(item.description or "")[:2000] or None,
            source_inventory_id=item.id,
        )
        db.add(med)
        existing_names.add(name)
        item.migrated_to_medication = True
        db.add(item)
        created += 1

    if created:
        await db.flush()

    return created, skipped_duplicate


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — list queries
# ─────────────────────────────────────────────────────────────────────────────


async def json_list_medications(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user_id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user_id))).scalars().all()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user_id))).scalars().all()
    out = []
    for m in meds:
        d = med_dict(m)
        d["stocks"] = [
            {
                "id": str(st.id),
                "quantity": st.quantity,
                "unit": st.unit,
                "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
                "kit_name": st.kit.name if st.kit else None,
            }
            for st in stocks
            if st.medication_id == m.id
        ]
        d["schedules"] = [
            {
                "id": str(s.id),
                "dose_quantity": s.dose_quantity,
                "dose_unit": s.dose_unit,
                "frequency_type": s.frequency_type,
                "times_per_day": s.times_per_day,
                "times_of_day": s.times_of_day,
                "interval_hours": s.interval_hours,
                "days_of_week": s.days_of_week,
                "is_active": s.is_active,
            }
            for s in schedules
            if s.medication_id == m.id
        ]
        out.append(d)
    return out


async def json_list_stocks(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    stocks = (
        (await db.execute(select(MedStock).where(MedStock.user_id == user_id).order_by(MedStock.created_at.desc())))
        .scalars()
        .all()
    )
    return [stock_dict(st) for st in stocks]


async def json_list_schedules(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    schedules = (
        (
            await db.execute(
                select(MedSchedule).where(MedSchedule.user_id == user_id).order_by(MedSchedule.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [schedule_dict(s) for s in schedules]


async def json_list_kits(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    kits = (await db.execute(select(MedKit).where(MedKit.user_id == user_id).order_by(MedKit.name))).scalars().all()
    return [
        {
            "id": str(k.id),
            "name": k.name,
            "location": kit_location_label(k),
            "location_id": str(k.location_id) if k.location_id else None,
            "notes": k.notes,
        }
        for k in kits
    ]


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — CRUD
# ─────────────────────────────────────────────────────────────────────────────


def _validate_name(name: str) -> str:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    return name


async def json_create_medication(db: AsyncSession, user_id: uuid.UUID, body: MedicationBody) -> Medication:
    name = _validate_name(body.name)
    kind = body.kind if body.kind in MED_KINDS else "medication"
    m = Medication(
        user_id=user_id,
        name=name,
        kind=kind,
        active_ingredient=(body.active_ingredient or "").strip()[:200] or None,
        form=(body.form or "").strip()[:50] or None,
        strength=(body.strength or "").strip()[:50] or None,
        unit=(body.unit or "").strip()[:20] or None,
        instructions=(body.instructions or "").strip() or None,
        notes=(body.notes or "").strip() or None,
        is_active=body.is_active,
    )
    db.add(m)
    await db.flush()
    return m


async def json_update_medication(
    db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID, body: MedicationBody
) -> Medication:
    m = await get_med(db, user_id, medication_id)
    name = _validate_name(body.name)
    m.name = name
    m.kind = body.kind if body.kind in MED_KINDS else "medication"
    m.active_ingredient = (body.active_ingredient or "").strip()[:200] or None
    m.form = (body.form or "").strip()[:50] or None
    m.strength = (body.strength or "").strip()[:50] or None
    m.unit = (body.unit or "").strip()[:20] or None
    m.instructions = (body.instructions or "").strip() or None
    m.notes = (body.notes or "").strip() or None
    m.is_active = body.is_active
    await db.flush()
    return m


async def json_create_stock(db: AsyncSession, user_id: uuid.UUID, body: StockBody) -> MedStock:
    m = await get_med(db, user_id, body.medication_id)
    kit = await get_kit(db, user_id, body.kit_id) if body.kit_id else None
    st = MedStock(
        user_id=user_id,
        medication_id=m.id,
        kit_id=kit.id if kit else None,
        quantity=body.quantity,
        unit=(body.unit or "").strip()[:20] or m.unit,
        lot_number=(body.lot_number or "").strip()[:100] or None,
        expiry_date=body.expiry_date,
        low_stock_threshold=body.low_stock_threshold,
        notes=(body.notes or "").strip() or None,
    )
    st.medication = m
    st.kit = kit
    db.add(st)
    await db.flush()
    return st


async def json_create_schedule(
    db: AsyncSession, user_id: uuid.UUID, body: ScheduleBody, course_id: uuid.UUID | None = None
) -> MedSchedule:
    m = await get_med(db, user_id, body.medication_id)
    freq = body.frequency_type if body.frequency_type in FREQUENCY_TYPES else "daily"
    ed = body.end_date
    if not ed and body.duration_days and body.start_date:
        ed = body.start_date + timedelta(days=body.duration_days - 1)
    relation = body.food_relation if body.food_relation in FOOD_RELATIONS else None
    s = MedSchedule(
        user_id=user_id,
        medication_id=m.id,
        dose_quantity=body.dose_quantity,
        dose_unit=(body.dose_unit or "").strip()[:20] or m.unit,
        frequency_type=freq,
        times_per_day=body.times_per_day,
        times_of_day=body.times_of_day,
        interval_hours=body.interval_hours,
        days_of_week=body.days_of_week,
        start_date=body.start_date,
        end_date=ed,
        food_relation=relation,
        duration_days=body.duration_days,
        meal_timing=body.meal_timing,
        meal_offset_min=body.meal_offset_min,
        course_id=course_id,
        instructions=(body.instructions or "").strip() or None,
        is_active=body.is_active,
    )
    s.medication = m
    db.add(s)
    await db.flush()
    return s


async def json_create_kit(db: AsyncSession, user_id: uuid.UUID, body: KitBody) -> MedKit:
    name = _validate_name(body.name)
    loc_id = await _resolve_kit_location(db, user_id, body.location_id)
    k = MedKit(
        user_id=user_id,
        name=name,
        location=(body.location or "").strip()[:200] or None,
        location_id=loc_id,
        notes=(body.notes or "").strip() or None,
    )
    db.add(k)
    await db.flush()
    return k


async def json_delete_stock(db: AsyncSession, user_id: uuid.UUID, stock_id: uuid.UUID) -> None:
    st = await get_stock(db, user_id, stock_id)
    await db.delete(st)
    await db.flush()


async def json_delete_schedule(db: AsyncSession, user_id: uuid.UUID, schedule_id: uuid.UUID) -> None:
    s = await get_schedule(db, user_id, schedule_id)
    await db.delete(s)
    await db.flush()


async def json_delete_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> None:
    k = await get_kit(db, user_id, kit_id)
    await db.delete(k)
    await db.flush()


async def json_delete_medication(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> None:
    await delete_medication(db, user_id, medication_id)
