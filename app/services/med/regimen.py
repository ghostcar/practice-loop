"""Regimen: meal timing, schedule times, free-text parser (ADR-189)."""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.models.medication import MedSchedule
from app.timeutils import local_today

EXPIRING_SOON_DAYS = 30

# ─────────────────────────────────────────────────────────────────────────────
# Constants: meal grid + offsets + presets
# ─────────────────────────────────────────────────────────────────────────────

MEAL_TIMES: dict[str, str] = {"breakfast": "08:00", "lunch": "13:00", "dinner": "19:00"}
MEAL_OFFSETS: dict[str, int] = {
    "before_meal": -30,
    "after_meal": 15,
    "during_meal": 0,
    "empty_stomach": -30,
    "independent": 0,
}

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
    {
        "key": "interval_hours",
        "i18n": "med_preset_interval_hours",
        "params": {"frequency_type": "interval"}},
    {
        "key": "weekly_days",
        "i18n": "med_preset_weekly_days",
        "params": {"frequency_type": "weekly", "times_per_day": 1},
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Time helpers
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Smart input (ADR-189, phase D): free-text regimen → structured params
# ─────────────────────────────────────────────────────────────────────────────

_WEEKDAY_3: dict[str, int] = {
    "пон": 0, "вто": 1, "сре": 2, "чет": 3, "пят": 4, "суб": 5, "вос": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}
_WEEKDAYS_RU: list[str] = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_WEEKDAYS_EN: list[str] = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_UNIT_SYN: dict[str, str] = {
    "табл": "tablet", "таблетк": "tablet", "капсул": "capsule", "капс": "capsule",
    "мл": "ml", "мг": "mg", "г": "g", "грамм": "g", "капл": "drop",
    "саше": "sachet", "пакет": "sachet", "доз": "dose",
    "tablet": "tablet", "tablets": "tablet", "capsule": "capsule",
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

    # старт с конкретного дня недели
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
        if (has_morning or has_evening) and not times_per_day:
            out["times_per_day"] = 1

    if duration:
        out["duration_days"] = duration

    content = {
        "dose_quantity", "dose_unit", "food_relation", "times_per_day",
        "times_of_day", "interval_hours", "days_of_week", "duration_days", "start_date",
    }
    if not (set(out) & content):
        raise ValueError("Could not parse regimen text")
    return out


FOOD_RELATION_LABELS: dict[str, str] = {
    "empty_stomach": "Натощак",
    "before_meal": "До еды",
    "during_meal": "Во время еды",
    "after_meal": "После еды",
    "independent": "Независимо от еды",
}


def group_meds_by_meal(items: list[dict]) -> list[dict]:
    """Группирует список препаратов слота по типу приёма пищи (ADR-207, этап 2)."""
    order = ["empty_stomach", "before_meal", "during_meal", "after_meal", "independent"]
    by_relation: dict[str, list[dict]] = {k: [] for k in order}
    for item in items:
        rel = item.get("food_relation") or "independent"
        if rel not in by_relation:
            rel = "independent"
        by_relation[rel].append(item)

    result = []
    for rel in order:
        if by_relation[rel]:
            result.append({
                "food_relation": rel,
                "label": FOOD_RELATION_LABELS.get(rel, "Независимо"),
                "meds": by_relation[rel],
                "all_taken": all(m.get("taken", False) for m in by_relation[rel]),
                "pending": any(not m.get("taken", False) for m in by_relation[rel]),
            })
    return result

