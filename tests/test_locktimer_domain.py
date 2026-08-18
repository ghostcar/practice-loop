"""Tests for LockTimer C1 domain — enums, state machines, duration, hashing, random."""

from __future__ import annotations

import pytest

from app.locktimer import enums
from app.locktimer.domain import (
    apply_extension,
    canonical_json,
    compute_seed_commitment,
    deterministic_random,
    generate_random_seed,
    make_occurrence_key,
    sha256_hex,
    validate_safety_stop_reason,
)


# ---------------------------------------------------------------------------
# Enums — exhaustive state/transition validation
# ---------------------------------------------------------------------------
class TestSessionStates:
    def test_all_states_have_transition_entry(self) -> None:
        for state in enums.SESSION_STATES:
            assert state in enums.SESSION_TRANSITIONS, f"Missing transition entry for {state}"

    def test_terminal_has_no_transitions(self) -> None:
        for state in ("completed", "safety_stopped", "cancelled_by_system"):
            assert enums.SESSION_TRANSITIONS[state] == frozenset()

    def test_draft_can_go_to_active(self) -> None:
        assert enums.can_transition(enums.SESSION_TRANSITIONS, "draft", "active")

    def test_active_cannot_return_to_draft(self) -> None:
        assert not enums.can_transition(enums.SESSION_TRANSITIONS, "active", "draft")

    def test_active_can_safety_stop(self) -> None:
        assert enums.can_transition(enums.SESSION_TRANSITIONS, "active", "safety_stopped")


class TestSlotStates:
    def test_pending_to_eligible(self) -> None:
        assert enums.can_transition(enums.SLOT_TRANSITIONS, "pending", "eligible")

    def test_open_to_closed(self) -> None:
        assert enums.can_transition(enums.SLOT_TRANSITIONS, "open", "closed")

    def test_closed_is_terminal(self) -> None:
        assert enums.is_terminal("closed", enums.TASK_TERMINAL_STATES) is False
        assert enums.SLOT_TRANSITIONS["closed"] == frozenset()


class TestTaskStates:
    def test_terminal_states_are_immutable(self) -> None:
        for state in enums.TASK_TERMINAL_STATES:
            assert enums.TASK_TRANSITIONS[state] == frozenset()

    def test_scheduled_to_visible(self) -> None:
        assert enums.can_transition(enums.TASK_TRANSITIONS, "scheduled", "visible")

    def test_visible_to_submitted(self) -> None:
        assert enums.can_transition(enums.TASK_TRANSITIONS, "visible", "submitted")

    def test_completed_is_terminal(self) -> None:
        assert enums.is_terminal("completed", enums.TASK_TERMINAL_STATES)
        assert enums.TASK_TRANSITIONS["completed"] == frozenset()


class TestSlotRuleTypes:
    def test_all_types_defined(self) -> None:
        assert len(enums.SLOT_RULE_TYPES) == 5


class TestTaskScheduleTypes:
    def test_all_types_defined(self) -> None:
        assert len(enums.TASK_SCHEDULE_TYPES) == 6


# ---------------------------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------------------------
class TestApplyExtension:
    def test_positive_extension(self) -> None:
        import datetime as dt

        start = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
        new_end, applied = apply_extension(start, 1800, None)
        assert applied == 1800
        assert new_end == dt.datetime(2026, 1, 1, 12, 30, tzinfo=dt.UTC)

    def test_clamped_by_max_end(self) -> None:
        import datetime as dt

        start = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
        max_end = dt.datetime(2026, 1, 1, 12, 10, tzinfo=dt.UTC)
        new_end, applied = apply_extension(start, 1800, max_end)
        assert new_end == max_end
        assert applied == 600

    def test_zero_extension(self) -> None:
        import datetime as dt

        start = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
        new_end, applied = apply_extension(start, 0, None)
        assert applied == 0
        assert new_end == start

    def test_negative_extension_returns_zero(self) -> None:
        import datetime as dt

        start = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
        new_end, applied = apply_extension(start, -100, None)
        assert applied == 0


# ---------------------------------------------------------------------------
# Canonical JSON & hashing
# ---------------------------------------------------------------------------
class TestCanonicalJSON:
    def test_sorted_keys(self) -> None:
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonical_json(obj)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_sha256_consistent(self) -> None:
        h1 = sha256_hex("hello")
        h2 = sha256_hex("hello")
        assert h1 == h2
        assert len(h1) == 64


# ---------------------------------------------------------------------------
# Deterministic random
# ---------------------------------------------------------------------------
class TestDeterministicRandom:
    def test_reproducible(self) -> None:
        v1 = deterministic_random("seed", "rule-1", 0)
        v2 = deterministic_random("seed", "rule-1", 0)
        assert v1 == v2

    def test_different_seed_different_value(self) -> None:
        v1 = deterministic_random("seed-a", "rule-1", 0)
        v2 = deterministic_random("seed-b", "rule-1", 0)
        assert v1 != v2

    def test_different_index_different_value(self) -> None:
        v1 = deterministic_random("seed", "rule-1", 0)
        v2 = deterministic_random("seed", "rule-1", 1)
        assert v1 != v2

    def test_in_range(self) -> None:
        for i in range(100):
            v = deterministic_random("seed", "rule-1", i)
            assert 0.0 <= v < 1.0


# ---------------------------------------------------------------------------
# Random seed
# ---------------------------------------------------------------------------
class TestRandomSeed:
    def test_generation(self) -> None:
        seed = generate_random_seed()
        assert len(seed) == 64  # 32 bytes hex

    def test_commitment(self) -> None:
        seed = generate_random_seed()
        commitment = compute_seed_commitment(seed)
        assert len(commitment) == 64

    def test_commitment_consistent(self) -> None:
        seed = "test"
        c1 = compute_seed_commitment(seed)
        c2 = compute_seed_commitment(seed)
        assert c1 == c2


# ---------------------------------------------------------------------------
# Occurrence key
# ---------------------------------------------------------------------------
class TestOccurrenceKey:
    def test_deterministic(self) -> None:
        k1 = make_occurrence_key("s1", "r1", 0)
        k2 = make_occurrence_key("s1", "r1", 0)
        assert k1 == k2

    def test_different_session(self) -> None:
        k1 = make_occurrence_key("s1", "r1", 0)
        k2 = make_occurrence_key("s2", "r1", 0)
        assert k1 != k2


# ---------------------------------------------------------------------------
# Safety stop
# ---------------------------------------------------------------------------
class TestSafetyStop:
    def test_valid_reasons(self) -> None:
        for reason in ("user_requested", "emergency", "consent_revoked"):
            assert validate_safety_stop_reason(reason) == reason

    def test_invalid_reason_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_safety_stop_reason("invalid_reason")
