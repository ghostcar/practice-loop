"""Task status constants and transition rules (ADR-040).

The strict 11-state enum replaces the loose ``pending/completed/interrupted``
strings. ``normalize_status`` maps legacy values during migration so old rows
and callers keep working.
"""

from __future__ import annotations

# --- Strict task status enum (ADR-040) ---

DRAFT = "draft"  # черновик
PLANNED = "planned"  # запланирована
IN_PROGRESS = "in_progress"  # начата
COMPLETED = "completed"  # выполнена
PARTIALLY_COMPLETED = "partially_completed"  # выполнена частично
SKIPPED = "skipped"  # пропущена
CANCELLED = "cancelled"  # отменена до начала
STOPPED = "stopped"  # начата и остановлена
SUBSTITUTED = "substituted"  # заменена другой задачей
NOT_APPLICABLE = "not_applicable"  # потеряла актуальность
REVIEW_NEEDED = "review_needed"  # требует заметки/обсуждения

TASK_STATUSES: tuple[str, ...] = (
    DRAFT,
    PLANNED,
    IN_PROGRESS,
    COMPLETED,
    PARTIALLY_COMPLETED,
    SKIPPED,
    CANCELLED,
    STOPPED,
    SUBSTITUTED,
    NOT_APPLICABLE,
    REVIEW_NEEDED,
)

# --- Legacy mapping (v0.8 → v0.9 status machine) ---

LEGACY_STATUS_MAP: dict[str, str] = {
    "pending": PLANNED,
    "interrupted": STOPPED,
    "completed": COMPLETED,
}


def normalize_status(value: str | None) -> str:
    """Map a legacy status (or raw value) onto the strict enum."""
    if value is None:
        return PLANNED
    return LEGACY_STATUS_MAP.get(value, value)


def is_valid_status(value: str) -> bool:
    return value in TASK_STATUSES


# --- Transition rules (ADR-040) ---
#
# Cancelling/skipping before start is always allowed (no penalty — ADR-038).
# ``stopped`` (started then interrupted) carries a penalty per ADR-029.

STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({PLANNED, CANCELLED}),
    PLANNED: frozenset(
        {
            IN_PROGRESS,
            COMPLETED,
            PARTIALLY_COMPLETED,
            SKIPPED,
            CANCELLED,
            STOPPED,  # ADR-029: interrupting a planned task still carries a penalty
            SUBSTITUTED,
            NOT_APPLICABLE,
            REVIEW_NEEDED,
            DRAFT,
        }
    ),
    IN_PROGRESS: frozenset({COMPLETED, PARTIALLY_COMPLETED, STOPPED, REVIEW_NEEDED}),
    COMPLETED: frozenset({REVIEW_NEEDED, PLANNED}),
    PARTIALLY_COMPLETED: frozenset({COMPLETED, STOPPED, REVIEW_NEEDED}),
    SKIPPED: frozenset({PLANNED, DRAFT}),
    CANCELLED: frozenset({PLANNED, DRAFT}),
    STOPPED: frozenset({IN_PROGRESS, REVIEW_NEEDED}),
    SUBSTITUTED: frozenset({PLANNED, DRAFT}),
    NOT_APPLICABLE: frozenset({PLANNED, DRAFT}),
    REVIEW_NEEDED: frozenset({PLANNED, IN_PROGRESS, COMPLETED, CANCELLED}),
}


def can_transition(from_status: str | None, to_status: str) -> bool:
    """Whether ``to_status`` is a legal next state from ``from_status``."""
    src = normalize_status(from_status)
    return to_status in STATUS_TRANSITIONS.get(src, frozenset())
