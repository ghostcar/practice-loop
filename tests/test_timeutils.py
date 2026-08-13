"""Tests for app.timeutils — naive→aware UTC normalization."""

from datetime import UTC, datetime

from app.timeutils import as_utc


def test_as_utc_passes_through_aware():
    aware = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)
    assert as_utc(aware) is aware


def test_as_utc_attaches_utc_to_naive():
    naive = datetime(2026, 8, 13, 12, 0, 0)
    result = as_utc(naive)
    assert result.tzinfo is UTC
    assert result == datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)


def test_as_utc_roundtrip():
    aware = datetime.now(UTC)
    naive = aware.replace(tzinfo=None)
    assert as_utc(naive) == aware
