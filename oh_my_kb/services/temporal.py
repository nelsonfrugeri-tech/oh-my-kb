"""Temporal helper — parse a human ``since`` string into a UTC datetime.

Accepted formats
----------------
* Relative  : ``"7d"``, ``"30d"``, ``"24h"``, ``"90m"`` — decimal digits
  followed by ``d`` (days), ``h`` (hours) or ``m`` (minutes).
* ISO date  : ``"2026-06-01"`` — interpreted as that date at ``00:00 UTC``.
* ISO datetime : any string accepted by :func:`datetime.fromisoformat` that
  already carries timezone info.  Naive datetimes (no tzinfo) are **rejected**
  — they are ambiguous and almost always a caller bug.

The ``now`` parameter is injected so callers can produce deterministic results
in tests without monkeypatching the real clock.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

# Pattern for relative formats: one or more digits followed by d/h/m.
_RELATIVE_RE = re.compile(r"^(\d+)([dhm])$")

# Pattern for an ISO date without time component (YYYY-MM-DD).
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_UNITS: dict[str, str] = {"d": "days", "h": "hours", "m": "minutes"}


def parse_since(value: str, *, now: datetime) -> datetime:
    """Return a tz-aware UTC datetime representing the start of the time window.

    ``now`` must be tz-aware.  The returned datetime is always tz-aware UTC.

    Raises
    ------
    ValueError
        If ``value`` does not match any accepted format, or if an ISO datetime
        string carries no timezone information.
    """
    stripped = value.strip()

    # --- relative ---------------------------------------------------------
    m = _RELATIVE_RE.match(stripped)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        delta = timedelta(**{_UNITS[unit]: amount})
        result = now - delta
        # Normalise to UTC regardless of what tz 'now' carries.
        return result.astimezone(UTC)

    # --- ISO date (YYYY-MM-DD) --------------------------------------------
    if _ISO_DATE_RE.match(stripped):
        # Midnight UTC on that date.
        return datetime.fromisoformat(stripped).replace(tzinfo=UTC)

    # --- ISO datetime with tzinfo ----------------------------------------
    try:
        dt = datetime.fromisoformat(stripped)
    except ValueError:
        pass
    else:
        if dt.tzinfo is None:
            raise ValueError(
                f"invalid 'since' value {value!r}; ISO datetimes must carry "
                "timezone info (e.g. '2026-06-01T00:00:00+00:00'). "
                "Accepted formats: '7d' / '24h' / '90m' / ISO date / ISO datetime with tz."
            )
        return dt.astimezone(UTC)

    raise ValueError(
        f"invalid 'since' value {value!r}; accepted: '7d'/'24h'/'90m' (relative), "
        "ISO date '2026-06-01', or ISO datetime '2026-06-01T00:00:00+00:00'."
    )
