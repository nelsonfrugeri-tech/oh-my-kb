"""Unit tests for :func:`~oh_my_kb.services.temporal.parse_since`.

All tests inject a fixed ``now`` so results are deterministic regardless of
when the suite runs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from oh_my_kb.services.temporal import parse_since

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
    """Unit 'w' (weeks) is not accepted by the current implementation."""
    with pytest.raises(ValueError, match="invalid 'since' value"):
        parse_since("2w", now=NOW)


def test_float_relative_rejected() -> None:
    """Only integers are accepted for relative durations."""
    with pytest.raises(ValueError, match="invalid 'since' value"):
        parse_since("1.5d", now=NOW)
