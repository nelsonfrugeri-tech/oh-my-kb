"""Unit tests for :func:`~oh_my_harness.kb.services.temporal.parse_since`.

All tests inject a fixed ``now`` so results are deterministic regardless of
when the suite runs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from oh_my_harness.kb.services.temporal import is_before_since, parse_since

# Fixed reference point used across all tests.
NOW = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Relative formats
# ---------------------------------------------------------------------------


def test_relative_days() -> None:
    result = parse_since("7d", now=NOW)
    assert result == NOW - timedelta(days=7)
    assert result.tzinfo is not None


def test_relative_hours() -> None:
    result = parse_since("24h", now=NOW)
    assert result == NOW - timedelta(hours=24)
    assert result.tzinfo is not None


def test_relative_minutes() -> None:
    result = parse_since("90m", now=NOW)
    assert result == NOW - timedelta(minutes=90)
    assert result.tzinfo is not None


def test_relative_30d() -> None:
    result = parse_since("30d", now=NOW)
    assert result == NOW - timedelta(days=30)


def test_relative_large_value() -> None:
    result = parse_since("365d", now=NOW)
    assert result == NOW - timedelta(days=365)


def test_relative_result_is_utc() -> None:
    """Result is always UTC regardless of the tz carried by ``now``."""
    tz_plus2 = timezone(timedelta(hours=2))
    now_local = datetime(2026, 6, 6, 14, 0, 0, tzinfo=tz_plus2)  # same instant as NOW
    result = parse_since("1d", now=now_local)
    # Result should be UTC and equal to NOW minus 1 day.
    assert result.tzinfo == UTC
    assert result == NOW - timedelta(days=1)


# ---------------------------------------------------------------------------
# ISO date
# ---------------------------------------------------------------------------


def test_iso_date_midnight_utc() -> None:
    result = parse_since("2026-06-01", now=NOW)
    assert result == datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    assert result.tzinfo is not None


def test_iso_date_another_date() -> None:
    result = parse_since("2025-01-15", now=NOW)
    assert result == datetime(2025, 1, 15, 0, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# ISO datetime with tzinfo
# ---------------------------------------------------------------------------


def test_iso_datetime_utc_offset() -> None:
    result = parse_since("2026-06-01T00:00:00+00:00", now=NOW)
    assert result == datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)


def test_iso_datetime_non_utc_tz_converted() -> None:
    # +02:00 → UTC should subtract 2 hours.
    result = parse_since("2026-06-01T12:00:00+02:00", now=NOW)
    assert result == datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Rejected inputs
# ---------------------------------------------------------------------------


def test_naive_iso_datetime_rejected() -> None:
    """ISO datetime without timezone info must be rejected."""
    with pytest.raises(ValueError, match="timezone info"):
        parse_since("2026-06-01T00:00:00", now=NOW)


def test_garbage_string_rejected() -> None:
    with pytest.raises(ValueError, match="invalid 'since' value"):
        parse_since("last-week", now=NOW)


def test_empty_ish_garbage_rejected() -> None:
    with pytest.raises(ValueError, match="invalid 'since' value"):
        parse_since("xyz", now=NOW)


def test_invalid_unit_rejected() -> None:
    """Unknown unit letters (e.g. 's' for seconds) must be rejected."""
    with pytest.raises(ValueError, match="invalid 'since' value"):
        parse_since("2s", now=NOW)


def test_float_relative_rejected() -> None:
    """Only integers are accepted for relative durations."""
    with pytest.raises(ValueError, match="invalid 'since' value"):
        parse_since("1.5d", now=NOW)


# ---------------------------------------------------------------------------
# Case-insensitive relative units (MAJOR fix)
# ---------------------------------------------------------------------------


def test_relative_accepts_uppercase_D() -> None:
    result = parse_since("7D", now=NOW)
    assert result == NOW - timedelta(days=7)
    assert result.tzinfo is not None


def test_relative_accepts_uppercase_H() -> None:
    result = parse_since("24H", now=NOW)
    assert result == NOW - timedelta(hours=24)
    assert result.tzinfo is not None


def test_relative_accepts_uppercase_M() -> None:
    result = parse_since("90M", now=NOW)
    assert result == NOW - timedelta(minutes=90)
    assert result.tzinfo is not None


def test_relative_accepts_uppercase_W() -> None:
    result = parse_since("2W", now=NOW)
    assert result == NOW - timedelta(weeks=2)
    assert result.tzinfo is not None


# ---------------------------------------------------------------------------
# Weeks support (MAJOR fix)
# ---------------------------------------------------------------------------


def test_relative_supports_weeks_lowercase() -> None:
    """'2w' must equal 14 days from now."""
    result = parse_since("2w", now=NOW)
    assert result == NOW - timedelta(weeks=2)
    assert result == NOW - timedelta(days=14)
    assert result.tzinfo is not None


def test_relative_supports_one_week() -> None:
    result = parse_since("1w", now=NOW)
    assert result == NOW - timedelta(days=7)


def test_relative_result_is_utc_for_weeks() -> None:
    """Week results are always UTC regardless of input tz."""
    tz_plus2 = timezone(timedelta(hours=2))
    now_local = datetime(2026, 6, 6, 14, 0, 0, tzinfo=tz_plus2)
    result = parse_since("1w", now=now_local)
    assert result.tzinfo == UTC
    assert result == NOW - timedelta(weeks=1)


# ---------------------------------------------------------------------------
# is_before_since helper (MAJOR fix)
# ---------------------------------------------------------------------------


def test_is_before_since_tz_aware_before() -> None:
    since = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    dt = datetime(2026, 5, 31, 23, 59, 59, tzinfo=UTC)
    assert is_before_since(dt, since) is True


def test_is_before_since_tz_aware_equal() -> None:
    since = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    dt = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    assert is_before_since(dt, since) is False


def test_is_before_since_tz_aware_after() -> None:
    since = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    dt = datetime(2026, 6, 2, 0, 0, 0, tzinfo=UTC)
    assert is_before_since(dt, since) is False


def test_is_before_since_tz_naive_treated_as_utc() -> None:
    """Tz-naive datetimes from payloads must be treated as UTC."""
    since = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    dt_naive = datetime(2026, 5, 31, 23, 0, 0)  # no tzinfo
    assert is_before_since(dt_naive, since) is True


def test_is_before_since_non_utc_tz_normalised() -> None:
    """Datetimes with non-UTC tz are correctly normalised before comparison."""
    since = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    # +02:00 → UTC is 10:00 UTC, which is before since (12:00 UTC)
    tz_plus2 = timezone(timedelta(hours=2))
    dt = datetime(2026, 6, 1, 12, 0, 0, tzinfo=tz_plus2)  # = 10:00 UTC
    assert is_before_since(dt, since) is True


def test_is_before_since_non_utc_tz_after_since() -> None:
    """Non-UTC tz dt that is after since must return False."""
    since = datetime(2026, 6, 1, 8, 0, 0, tzinfo=UTC)
    tz_plus2 = timezone(timedelta(hours=2))
    dt = datetime(2026, 6, 1, 12, 0, 0, tzinfo=tz_plus2)  # = 10:00 UTC, after 08:00 UTC
    assert is_before_since(dt, since) is False
