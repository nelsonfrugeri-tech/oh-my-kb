"""Locale resolution for instruction-layer content (skills, templates, agent rules).

Single source of truth for the active locale and fallback algorithm.
To change the project-wide locale (future language-option feature),
only DEFAULT_LOCALE needs to change.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_LOCALE: str = "pt-BR"
BASE_LOCALE: str = "pt-BR"


def resolve_locale_path(
    base_dir: Path,
    filename: str,
    locale: str = DEFAULT_LOCALE,
) -> Path:
    """Return the path to `filename` under `base_dir / locale`, with fallback.

    Lookup order:
        1. base_dir / locale / filename
        2. base_dir / BASE_LOCALE / filename  (only when locale != BASE_LOCALE)

    Raises:
        FileNotFoundError: when neither the requested locale nor the base
            locale contain `filename`; names both paths tried.
    """
    requested = base_dir / locale / filename
    if requested.is_file():
        return requested

    if locale != BASE_LOCALE:
        fallback = base_dir / BASE_LOCALE / filename
        if fallback.is_file():
            return fallback
        raise FileNotFoundError(
            f"Locale file {filename!r} not found. Tried: {requested}, {fallback}"
        )

    raise FileNotFoundError(
        f"Locale file {filename!r} not found. Tried: {requested}"
    )
