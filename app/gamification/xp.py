"""XP calculation engine: formulas, level thresholds, streak/kombo multipliers."""

from datetime import UTC, datetime

# Level thresholds (cumulative XP)
LEVEL_THRESHOLDS = [
    0,  # lvl 1
    100,  # lvl 2
    250,  # lvl 3
    500,  # lvl 4
    1000,  # lvl 5
    1750,  # lvl 6
    2750,  # lvl 7
    4000,  # lvl 8
    5500,  # lvl 9
    7500,  # lvl 10
    10000,  # lvl 11
    13000,  # lvl 12
    16500,  # lvl 13
    20500,  # lvl 14
    25000,  # lvl 15
]


def xp_for_level(level: int) -> int:
    """XP required to reach this level (cumulative)."""
    if level <= 0:
        return 0
    if level <= len(LEVEL_THRESHOLDS):
        return LEVEL_THRESHOLDS[level - 1]
    # Extend: each level beyond threshold list costs 2500 more
    return LEVEL_THRESHOLDS[-1] + (level - len(LEVEL_THRESHOLDS)) * 2500


def level_from_xp(xp: int) -> int:
    """Calculate level from total XP."""
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp < threshold:
            return i
    # Extended levels
    extra = (xp - LEVEL_THRESHOLDS[-1]) // 2500
    return len(LEVEL_THRESHOLDS) + extra


def xp_progress(xp: int) -> tuple[int, int, int]:
    """Return (current_level, xp_in_current_level, xp_needed_for_next)."""
    level = level_from_xp(xp)
    current_threshold = xp_for_level(level)
    next_threshold = xp_for_level(level + 1)
    return level, xp - current_threshold, next_threshold - current_threshold


# Base XP per task type
BASE_XP = {
    "one_time": 25,
    "series": 50,
    "infinite": 15,
}

# Streak bonus per day
STREAK_BONUS_PER_DAY = 5  # +5 XP per streak day

# Combo multiplier (10% per consecutive completion, cap +50%)
COMBO_MULTIPLIER_STEP = 0.10
COMBO_MULTIPLIER_CAP = 0.50


def calculate_task_xp(
    entity_type: str = "one_time",
    intensity: int = 1,
    streak_days: int = 0,
    combo_count: int = 0,
) -> int:
    """Calculate XP earned for completing a single task.

    Formula: base_xp(type) + streak_bonus + combo_multiplier
    """
    base = BASE_XP.get(entity_type, 25)

    # Streak bonus
    streak_bonus = streak_days * STREAK_BONUS_PER_DAY

    # Combo multiplier
    combo_mult = min(combo_count * COMBO_MULTIPLIER_STEP, COMBO_MULTIPLIER_CAP)
    combo_bonus = int(base * combo_mult)

    # Intensity bonus: +10% per intensity level above 1
    intensity_bonus = int(base * (intensity - 1) * 0.10)

    return base + streak_bonus + combo_bonus + intensity_bonus


def calculate_penalty_xp(xp: int, escalation: int = 1) -> int:
    """Calculate XP penalty for an interrupted task.

    Escalation multiplier: ×1, ×1.5, ×2, … (caps at ×5)
    """
    mult = min(1.0 + (escalation - 1) * 0.5, 5.0)
    return int(xp * mult)


def should_reset_streak(last_activity_date: datetime | None) -> bool:
    """Check if the streak should be reset (no activity yesterday)."""
    if last_activity_date is None:
        return False  # First activity — no reset
    today = datetime.now(UTC).date()
    last_date = last_activity_date.date() if hasattr(last_activity_date, "date") else last_activity_date
    return (today - last_date).days > 1
