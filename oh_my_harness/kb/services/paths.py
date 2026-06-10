"""Shared path conventions — universe data-root helpers.

Both CLI and MCP adapters need to resolve a notes-root directory from
``KB_NOTES_ROOT`` and a universe slug.  Keeping this logic in the ``services``
layer (neutral between adapters) prevents ``mcp/`` from importing ``cli/``.

``cli/paths.py`` re-exports :data:`DATA_ROOT_ENV` and
:func:`default_notes_root_for` from here to preserve its existing public
surface.

``NOTES_ROOT_ENV`` and :func:`get_notes_root` are compatibility aliases kept
so that :mod:`oh_my_harness.kb.services` (the package public surface) does not need to
import the now-deleted ``services/config`` module.
"""

from __future__ import annotations

import os
from pathlib import Path

from oh_my_harness.kb.core import slugify

DATA_ROOT_ENV = "KB_NOTES_ROOT"
# Compatibility alias — same env var string.
# New code should use DATA_ROOT_ENV; NOTES_ROOT_ENV kept for the services public surface.
NOTES_ROOT_ENV = DATA_ROOT_ENV

DEFAULT_DATA_ROOT = Path.home() / "oh-my-harness"


def get_data_root() -> Path:
    """Return the data root (parent of every universe directory)."""
    raw = os.environ.get(DATA_ROOT_ENV)
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_DATA_ROOT


# Compatibility alias — ``get_notes_root`` was the original name exported by
# the now-deleted ``services/config`` module.
# New code should call get_data_root() directly.
get_notes_root = get_data_root


def default_notes_root_for(universe: str, data_root: Path | None = None) -> Path:
    """Return the default notes-root path for ``universe``.

    Result: ``data_root / slug(universe)``.  ``data_root`` defaults to
    :func:`get_data_root` so callers don't have to thread it through.
    """
    base = data_root if data_root is not None else get_data_root()
    return base / slugify(universe)
