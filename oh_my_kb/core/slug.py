"""Slug generation for note filenames.

A note's slug is the human-readable component of its filename: a date prefix
followed by an ASCII-folded, hyphenated form of the title. The slug is *not*
the canonical identifier (that role belongs to the UUID `id`), so it is safe
to regenerate or rename without breaking cross-note links.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

_NON_ALPHANUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, strip accents, collapse non-alphanumeric runs to hyphens."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return _NON_ALPHANUM.sub("-", ascii_only.lower()).strip("-")


def generate_slug(title: str, created_at: datetime) -> str:
    """Return ``YYYY-MM-DD-<slugified-title>`` for the given note metadata."""
    date_prefix = created_at.strftime("%Y-%m-%d")
    body = slugify(title)
    return f"{date_prefix}-{body}" if body else date_prefix
