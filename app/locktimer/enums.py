"""LockTimer domain enums — session/slot/task states, rule types, duration types."""

# Session states (04_DESIGN.md §6)
SESSION_DRAFT = "draft"
SESSION_VALIDATING = "validating"
SESSION_ACTIVE = "active"
SESSION_COMPLETED = "completed"
SESSION_SAFETY_STOPPED = "safety_stopped"
SESSION_CANCELLED_BY_SYSTEM = "cancelled_by_system"

SESSION_STATES: frozenset[str] = frozenset(
    {
        SESSION_DRAFT,
        SESSION_VALIDATING,
        SESSION_ACTIVE,
        SESSION_COMPLETED,
        SESSION_SAFETY_STOPPED,
        SESSION_CANCELLED_BY_SYSTEM,
    }
)

# Session → allowed next states
SESSION_TRANSITIONS: dict[str, frozenset[str]] = {
    SESSION_DRAFT: frozenset({SESSION_VALIDATING, SESSION_ACTIVE}),
    SESSION_VALIDATING: frozenset({SESSION_DRAFT, SESSION_ACTIVE}),
    SESSION_ACTIVE: frozenset({SESSION_COMPLETED, SESSION_SAFETY_STOPPED, SESSION_CANCELLED_BY_SYSTEM}),
    # Terminal states — no transitions.
    SESSION_COMPLETED: frozenset(),
    SESSION_SAFETY_STOPPED: frozenset(),
    SESSION_CANCELLED_BY_SYSTEM: frozenset(),
}

# Duration types (LT-COR-002)
DURATION_FIXED_DATES = "fixed_dates"
DURATION_FROM_START = "duration_from_start"
DURATION_INFINITE = "infinite"

DURATION_TYPES: frozenset[str] = frozenset({DURATION_FIXED_DATES, DURATION_FROM_START, DURATION_INFINITE})

# ---------------------------------------------------------------------------
# Slot states (04_DESIGN.md §6)
# ---------------------------------------------------------------------------
SLOT_PENDING = "pending"
SLOT_ELIGIBLE = "eligible"
SLOT_OPEN = "open"
SLOT_CLOSED = "closed"
SLOT_OVERDUE_OPEN = "overdue_open"  # computed status
SLOT_MISSED = "missed"
SLOT_BLOCKED = "blocked"
SLOT_CANCELLED = "cancelled"

SLOT_STATES: frozenset[str] = frozenset(
    {
        SLOT_PENDING,
        SLOT_ELIGIBLE,
        SLOT_OPEN,
        SLOT_CLOSED,
        SLOT_MISSED,
        SLOT_BLOCKED,
        SLOT_CANCELLED,
    }
)

SLOT_TRANSITIONS: dict[str, frozenset[str]] = {
    SLOT_PENDING: frozenset({SLOT_ELIGIBLE, SLOT_BLOCKED, SLOT_CANCELLED}),
    SLOT_ELIGIBLE: frozenset({SLOT_OPEN, SLOT_MISSED}),
    SLOT_OPEN: frozenset({SLOT_CLOSED}),
    SLOT_CLOSED: frozenset(),
    SLOT_MISSED: frozenset(),
    SLOT_BLOCKED: frozenset(),
    SLOT_CANCELLED: frozenset(),
}

# Slot rule types (LT-SLT-001)
SLOT_RULE_EVERY_N_DAYS = "every_n_days"
SLOT_RULE_EXACT_DATETIME = "exact_datetime"
SLOT_RULE_RECURRING_FROM_DATE = "recurring_from_date"
SLOT_RULE_FLEXIBLE_WINDOW_ONCE = "flexible_window_once"
SLOT_RULE_AFTER_PREVIOUS_CLOSE = "after_previous_close"

SLOT_RULE_TYPES: frozenset[str] = frozenset(
    {
        SLOT_RULE_EVERY_N_DAYS,
        SLOT_RULE_EXACT_DATETIME,
        SLOT_RULE_RECURRING_FROM_DATE,
        SLOT_RULE_FLEXIBLE_WINDOW_ONCE,
        SLOT_RULE_AFTER_PREVIOUS_CLOSE,
    }
)

# ---------------------------------------------------------------------------
# Task states (04_DESIGN.md §6)
# ---------------------------------------------------------------------------
TASK_SCHEDULED = "scheduled"
TASK_VISIBLE = "visible"
TASK_SUBMITTED = "submitted"
TASK_VERIFYING = "verifying"
TASK_COMPLETED = "completed"
TASK_REVIEW_REQUIRED = "review_required"
TASK_FAILED = "failed"
TASK_SKIPPED = "skipped"
TASK_EXPIRED = "expired"
TASK_SAFETY_CANCELLED = "safety_cancelled"

TASK_STATES: frozenset[str] = frozenset(
    {
        TASK_SCHEDULED,
        TASK_VISIBLE,
        TASK_SUBMITTED,
        TASK_VERIFYING,
        TASK_COMPLETED,
        TASK_REVIEW_REQUIRED,
        TASK_FAILED,
        TASK_SKIPPED,
        TASK_EXPIRED,
        TASK_SAFETY_CANCELLED,
    }
)

TASK_TERMINAL_STATES: frozenset[str] = frozenset(
    {TASK_COMPLETED, TASK_FAILED, TASK_SKIPPED, TASK_EXPIRED, TASK_SAFETY_CANCELLED}
)

TASK_TRANSITIONS: dict[str, frozenset[str]] = {
    TASK_SCHEDULED: frozenset({TASK_VISIBLE, TASK_EXPIRED, TASK_SKIPPED, TASK_SAFETY_CANCELLED}),
    TASK_VISIBLE: frozenset({TASK_SUBMITTED, TASK_SKIPPED, TASK_EXPIRED, TASK_SAFETY_CANCELLED}),
    TASK_SUBMITTED: frozenset({TASK_VERIFYING, TASK_COMPLETED, TASK_REVIEW_REQUIRED, TASK_FAILED}),
    TASK_VERIFYING: frozenset({TASK_COMPLETED, TASK_REVIEW_REQUIRED, TASK_FAILED}),
    TASK_REVIEW_REQUIRED: frozenset({TASK_COMPLETED, TASK_FAILED}),
    # Terminal
    TASK_COMPLETED: frozenset(),
    TASK_FAILED: frozenset(),
    TASK_SKIPPED: frozenset(),
    TASK_EXPIRED: frozenset(),
    TASK_SAFETY_CANCELLED: frozenset(),
}

# Task schedule types (LT-TSK-001)
TASK_SCHED_DAILY = "daily"
TASK_SCHED_EVERY_N_DAYS = "every_n_days"
TASK_SCHED_RECURRING_FROM_DATE = "recurring_from_date"
TASK_SCHED_EXACT_DATETIME = "exact_datetime"
TASK_SCHED_ANYTIME_BEFORE_END = "anytime_before_end"
TASK_SCHED_DETERMINISTIC_RANDOM = "deterministic_random"

TASK_SCHEDULE_TYPES: frozenset[str] = frozenset(
    {
        TASK_SCHED_DAILY,
        TASK_SCHED_EVERY_N_DAYS,
        TASK_SCHED_RECURRING_FROM_DATE,
        TASK_SCHED_EXACT_DATETIME,
        TASK_SCHED_ANYTIME_BEFORE_END,
        TASK_SCHED_DETERMINISTIC_RANDOM,
    }
)

# ---------------------------------------------------------------------------
# Penalty types (LT-PEN-001: Core allowlist)
# ---------------------------------------------------------------------------
PENALTY_ADD_TIME = "add_time"
PENALTY_BLOCK_NEXT_SLOT = "block_next_slot"
PENALTY_MARK_TASK_FAILED = "mark_task_failed"
PENALTY_POINTS = "points"

PENALTY_TYPES: frozenset[str] = frozenset(
    {PENALTY_ADD_TIME, PENALTY_BLOCK_NEXT_SLOT, PENALTY_MARK_TASK_FAILED, PENALTY_POINTS}
)

# Penalty event states
PENALTY_APPLIED = "applied"
PENALTY_CAPPED_NOOP = "capped_noop"
PENALTY_REJECTED = "rejected"
PENALTY_SUPERSEDED = "superseded"

PENALTY_EVENT_STATES: frozenset[str] = frozenset(
    {PENALTY_APPLIED, PENALTY_CAPPED_NOOP, PENALTY_REJECTED, PENALTY_SUPERSEDED}
)

# ---------------------------------------------------------------------------
# Job / outbox states
# ---------------------------------------------------------------------------
JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"
JOB_DEAD = "dead"

OUTBOX_PENDING = "pending"
OUTBOX_PUBLISHED = "published"
OUTBOX_FAILED = "failed"


def can_transition(state_map: dict[str, frozenset[str]], current: str, target: str) -> bool:
    """Check if a transition is allowed in the given state map."""
    return target in state_map.get(current, frozenset())


def is_terminal(state: str, terminal_set: frozenset[str]) -> bool:
    return state in terminal_set
