"""Time utilities — timezone-aware datetime helpers.

Centralizes naive→aware normalization and client-timezone "today" boundaries.

SQLAlchemy ``DateTime(timezone=True)`` columns return timezone-aware datetimes
on PostgreSQL but *naive* datetimes on SQLite (used by the test suite), so any
value read back from the DB must be normalized before being compared against
``datetime.now(UTC)``.

The request-scoped client timezone (IANA name, e.g. ``Europe/Moscow``) is
propagated via a ``ContextVar`` set by middleware from the ``client_tz``
cookie (written by app.js via ``Intl``). Day-boundary helpers fall back to UTC
when no timezone is set (background jobs, tests, no-JS clients).
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_client_tz: ContextVar[str | None] = ContextVar("client_tz", default=None)


def as_utc(dt: datetime) -> datetime:
    """Return ``dt`` as a timezone-aware datetime.

    Naive datetimes (e.g. read from SQLite) are assumed to already be in UTC
    and get a ``UTC`` tzinfo attached. Aware datetimes are returned unchanged.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def set_client_tz(tz: str | None) -> Token:
    """Set the request-scoped client timezone (IANA name, or None)."""
    return _client_tz.set(tz)


def reset_client_tz(token: Token) -> None:
    """Reset the request-scoped client timezone to its previous value."""
    _client_tz.reset(token)


def get_client_tz() -> str | None:
    """Return the current request's client timezone, or None."""
    return _client_tz.get()


def client_tzinfo() -> tzinfo | None:
    """Return the client's ``tzinfo``, or None if unset/invalid."""
    tz = _client_tz.get()
    if tz:
        try:
            return ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            return None
    return None


def resolve_tz(name: str | None) -> tzinfo:
    """Resolve an IANA timezone name to a ``tzinfo``, falling back to UTC.

    Used by background jobs (no request ContextVar) via ``settings`` and by
    day-boundary helpers. Invalid or missing names degrade to UTC.
    """
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return UTC


def local_today() -> date:
    """Calendar 'today' in the client's timezone (UTC fallback)."""
    z = client_tzinfo()
    return datetime.now(z or UTC).date()


def local_date(dt: datetime | None) -> date | None:
    """Convert a stored (UTC) datetime to the client-tz calendar date."""
    if dt is None:
        return None
    z = client_tzinfo()
    return as_utc(dt).astimezone(z or UTC).date()


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Return the [start, next-day-00:00) of a local-calendar day as aware UTC datetimes.

    Uses the request-scoped client timezone (client_tz cookie ContextVar) with a
    UTC fallback for background jobs and no-JS clients, matching ``local_today()``
    and ``local_date()``. Use these bounds when querying timestamptz columns by
    local calendar day — bare ISO date strings are rejected by PostgreSQL
    (``operator does not exist: timestamp with time zone <= character varying``).
    """
    z = client_tzinfo() or UTC
    start = datetime.combine(day, time.min, tzinfo=z).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=z).astimezone(UTC)
    return start, end
