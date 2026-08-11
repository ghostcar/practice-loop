"""LockTimer domain — pure value objects and state machines.

No SQLAlchemy, FastAPI, or network imports allowed in this module.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------------------------

MIN_SESSION_DURATION_SECONDS = 3600  # 1 hour (CORE-003, test mode may use 60)
MIN_SLOT_DURATION_SECONDS = 60
MAX_SLOT_DURATION_SECONDS = 86400  # 24 hours
MAX_LATE_SECONDS = 604800  # 7 days
MIN_DUE_WINDOW_SECONDS = 60
MAX_DUE_WINDOW_SECONDS = 2592000  # 30 days
DEFAULT_MERGE_GAP_SECONDS = 3600
DEFAULT_ROLLING_HORIZON_DAYS = 90
DEFAULT_REFILL_THRESHOLD_DAYS = 30


def clamp_effective_end(
    effective: datetime,
    max_end: datetime | None,
    original_end: datetime | None,
) -> datetime:
    """Clamp effective_end_at to max_end_at bounds."""
    if max_end is not None and effective > max_end:
        return max_end
    return effective


def apply_extension(
    current_end: datetime,
    extension_seconds: int,
    max_end: datetime | None,
) -> tuple[datetime, int]:
    """Add extension_seconds to current_end, clamp, return (new_end, applied_seconds)."""
    if extension_seconds <= 0:
        return current_end, 0
    new_end = current_end + timedelta(seconds=extension_seconds)
    if max_end is not None and new_end > max_end:
        new_end = max_end
    applied = int((new_end - current_end).total_seconds())
    return new_end, max(applied, 0)


# ---------------------------------------------------------------------------
# Canonical JSON & hashing
# ---------------------------------------------------------------------------


def canonical_json(obj: dict | list) -> str:
    """Serialize with sorted keys and normalized ISO datetimes."""
    return json.dumps(obj, sort_keys=True, default=_json_default, separators=(",", ":"))


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o)} is not JSON serializable")


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Deterministic random (from encrypted seed)
# ---------------------------------------------------------------------------


def deterministic_random(seed: str, rule_id: str, occurrence_index: int) -> float:
    """Produce reproducible float in [0, 1) from seed + rule_id + index."""
    payload = f"{seed}:{rule_id}:{occurrence_index}"
    digest = hashlib.sha256(payload.encode()).digest()
    # Take first 8 bytes as unsigned 64-bit integer, normalize to [0, 1).
    val = int.from_bytes(digest[:8], "big")
    return val / (2**64)


# ---------------------------------------------------------------------------
# Random seed generation
# ---------------------------------------------------------------------------


def generate_random_seed() -> str:
    """Return a hex-encoded random 32-byte seed."""
    return secrets.token_hex(32)


def compute_seed_commitment(seed: str) -> str:
    return sha256_hex(seed)


# ---------------------------------------------------------------------------
# Occurrence key (deterministic)
# ---------------------------------------------------------------------------


def make_occurrence_key(session_id: str, rule_id: str, index: int) -> str:
    return sha256_hex(f"{session_id}:{rule_id}:{index}")


# ---------------------------------------------------------------------------
# Safety stop result
# ---------------------------------------------------------------------------

SAFETY_STOP_REASONS: frozenset[str] = frozenset({"user_requested", "emergency", "consent_revoked"})


def validate_safety_stop_reason(reason_code: str) -> str:
    if reason_code not in SAFETY_STOP_REASONS:
        raise ValueError(f"Invalid safety stop reason: {reason_code}")
    return reason_code
