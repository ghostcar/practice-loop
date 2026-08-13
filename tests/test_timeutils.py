"""Tests for app.timeutils — naive→aware UTC normalization + localtime helper."""

from datetime import UTC, date, datetime

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


def test_local_today_utc_fallback():
    from app.timeutils import local_today

    assert local_today() == datetime.now(UTC).date()


def test_local_today_with_client_tz():
    from app.timeutils import client_tzinfo, local_today, reset_client_tz, set_client_tz

    token = set_client_tz("America/New_York")
    try:
        assert client_tzinfo() is not None
        assert isinstance(local_today(), date)
    finally:
        reset_client_tz(token)
    assert client_tzinfo() is None  # restored


def test_local_date_naive_assumed_utc():
    from app.timeutils import local_date

    naive = datetime(2026, 8, 13, 23, 30, 0)
    assert local_date(naive) == date(2026, 8, 13)  # no tz → UTC date


def test_local_date_converts_to_client_tz():
    from app.timeutils import local_date, reset_client_tz, set_client_tz

    token = set_client_tz("Asia/Tokyo")  # UTC+9
    try:
        # 2026-08-13 23:30 UTC == 2026-08-14 08:30 Tokyo
        assert local_date(datetime(2026, 8, 13, 23, 30, 0)) == date(2026, 8, 14)
    finally:
        reset_client_tz(token)


def test_invalid_tz_falls_back_to_utc():
    from app.timeutils import client_tzinfo, local_today, reset_client_tz, set_client_tz

    token = set_client_tz("Not/AZone")
    try:
        assert client_tzinfo() is None
        assert local_today() == datetime.now(UTC).date()
    finally:
        reset_client_tz(token)


def test_resolve_tz_valid():
    from app.timeutils import resolve_tz

    assert str(resolve_tz("Asia/Tokyo")) == "Asia/Tokyo"


def test_resolve_tz_invalid_falls_back_to_utc():
    from app.timeutils import resolve_tz

    assert resolve_tz("Not/AZone") is UTC


def test_resolve_tz_none_is_utc():
    from app.timeutils import resolve_tz

    assert resolve_tz(None) is UTC
