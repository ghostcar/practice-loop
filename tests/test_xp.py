"""Unit tests for XP engine: calculation, levels, streaks, penalties."""

from datetime import UTC, datetime, timedelta

from app.gamification.xp import (
    calculate_penalty_xp,
    calculate_task_xp,
    level_from_xp,
    should_reset_streak,
    xp_for_level,
    xp_progress,
)


class TestLevelThresholds:
    """Test level progression."""

    def test_level_1_xp_requirement(self):
        """Level 1 requires 0 XP."""
        assert xp_for_level(1) == 0

    def test_level_2_xp_requirement(self):
        """Level 2 requires 100 XP."""
        assert xp_for_level(2) == 100

    def test_level_5_xp_requirement(self):
        """Level 5 requires 1000 XP."""
        assert xp_for_level(5) == 1000

    def test_level_10_xp_requirement(self):
        """Level 10 requires 7500 XP."""
        assert xp_for_level(10) == 7500

    def test_level_from_xp_zero(self):
        """0 XP = level 1."""
        assert level_from_xp(0) == 1

    def test_level_from_xp_50(self):
        """50 XP is still level 1."""
        assert level_from_xp(50) == 1

    def test_level_from_xp_150(self):
        """150 XP = level 2 (threshold 100)."""
        assert level_from_xp(150) == 2

    def test_level_from_xp_999(self):
        """999 XP = level 4."""
        assert level_from_xp(999) == 4

    def test_level_from_xp_2000(self):
        """2000 XP = level 6 (threshold 1750)."""
        assert level_from_xp(2000) == 6

    def test_xp_progress_mid_level(self):
        """XP progress within a level."""
        level, current, needed = xp_progress(150)
        assert level == 2
        assert current == 50  # 150 - 100
        assert needed == 150  # 250 - 100

    def test_xp_progress_at_threshold(self):
        """Exactly at threshold."""
        level, current, needed = xp_progress(100)
        assert level == 2
        assert current == 0
        assert needed == 150


class TestXpCalculation:
    """Test XP earned for completing tasks."""

    def test_base_one_time(self):
        """One-time task base XP = 25."""
        xp = calculate_task_xp(entity_type="one_time")
        assert xp == 25

    def test_base_series(self):
        """Series task base XP = 50."""
        xp = calculate_task_xp(entity_type="series")
        assert xp == 50

    def test_base_infinite(self):
        """Infinite task base XP = 15."""
        xp = calculate_task_xp(entity_type="infinite")
        assert xp == 15

    def test_unknown_type_defaults_to_one_time(self):
        """Unknown type defaults to one_time base."""
        xp = calculate_task_xp(entity_type="custom")
        assert xp == 25

    def test_streak_bonus(self):
        """+5 XP per streak day."""
        xp = calculate_task_xp(entity_type="one_time", streak_days=5)
        assert xp == 25 + 25  # base + 5*5

    def test_combo_bonus(self):
        """+10% per combo, capped at +50%."""
        # combo_count=2 → +20%
        xp = calculate_task_xp(entity_type="one_time", combo_count=2)
        expected = 25 + int(25 * 0.20)  # 25 + 5 = 30
        assert xp == expected

    def test_combo_cap(self):
        """Combo multiplier caps at +50%."""
        xp = calculate_task_xp(entity_type="one_time", combo_count=100)
        max_combo = int(25 * 0.50)
        assert xp == 25 + max_combo

    def test_intensity_bonus(self):
        """+10% per intensity level above 1."""
        xp = calculate_task_xp(entity_type="one_time", intensity=3)
        expected = 25 + int(25 * 0.20)  # +20% for intensity 3
        assert xp == expected

    def test_all_bonuses_combined(self):
        """Streak + combo + intensity stack."""
        xp = calculate_task_xp(
            entity_type="series",  # base 50
            streak_days=3,  # +15
            combo_count=3,  # +15 (50*0.30)
            intensity=4,  # +15 (50*0.30)
        )
        expected = 50 + 15 + 15 + 15  # = 95
        assert xp == expected


class TestPenaltyCalculation:
    """Test XP penalty for interrupted tasks."""

    def test_no_escalation(self):
        """Escalation 1 = ×1 multiplier."""
        penalty = calculate_penalty_xp(25, escalation=1)
        assert penalty == 25

    def test_escalation_2(self):
        """Escalation 2 = ×1.5 multiplier."""
        penalty = calculate_penalty_xp(25, escalation=2)
        assert penalty == int(25 * 1.5)

    def test_escalation_max_cap(self):
        """Escalation multiplier caps at ×5."""
        penalty = calculate_penalty_xp(25, escalation=100)
        assert penalty == 25 * 5


class TestStreakReset:
    """Test streak reset logic."""

    def test_first_activity_no_reset(self):
        """No previous date — no reset."""
        assert not should_reset_streak(None)

    def test_today_no_reset(self):
        """Activity today — no reset."""
        today_dt = datetime.now(UTC)
        assert not should_reset_streak(today_dt)

    def test_yesterday_no_reset(self):
        """Activity yesterday — no reset (streak continues)."""
        yesterday = datetime.now(UTC) - timedelta(days=1)
        assert not should_reset_streak(yesterday)

    def test_two_days_ago_reset(self):
        """Activity 2+ days ago — reset."""
        two_days = datetime.now(UTC) - timedelta(days=2)
        assert should_reset_streak(two_days)
