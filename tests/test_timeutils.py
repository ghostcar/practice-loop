"""Tests for app.timeutils — naive→aware UTC normalization + localtime helper."""

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


def test_localtime_renders_time_element():
    from app.templates_setup import _localtime

    out = str(_localtime(datetime(2026, 8, 13, 12, 30, 0, tzinfo=UTC), "%Y-%m-%d %H:%M"))
    assert '<time datetime="2026-08-13T12:30:00+00:00"' in out
    assert 'data-tz-fmt="%Y-%m-%d %H:%M"' in out
    assert "2026-08-13 12:30" in out


def test_localtime_naive_assumed_utc():
    from app.templates_setup import _localtime

    out = str(_localtime(datetime(2026, 8, 13, 12, 30, 0), "%H:%M"))
    assert 'datetime="2026-08-13T12:30:00+00:00"' in out


def test_localtime_none_is_empty():
    from app.templates_setup import _localtime

    assert str(_localtime(None)) == ""
