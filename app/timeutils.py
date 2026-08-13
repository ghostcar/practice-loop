"""Time utilities — timezone-aware datetime helpers.

Centralizes naive→aware normalization. SQLAlchemy ``DateTime(timezone=True)``
columns return timezone-aware datetimes on PostgreSQL but *naive* datetimes on
SQLite (used by the test suite), so any value read back from the DB must be
normalized before being compared against ``datetime.now(UTC)``.
"""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(dt: datetime) -> datetime:
    """Return ``dt`` as a timezone-aware datetime.

    Naive datetimes (e.g. read from SQLite) are assumed to already be in UTC
    and get a ``UTC`` tzinfo attached. Aware datetimes are returned unchanged.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
