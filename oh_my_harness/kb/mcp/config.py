"""MCP server configuration.

A single ``KB_UNIVERSE`` env var binds the running server to one universe;
the active notes_root is derived from it via the same conventions the CLI
uses (:func:`oh_my_harness.kb.services.paths.default_notes_root_for`). Future
iterations may read the active universe from the TOML config written by
``omk`` — this module is the choke-point where that change will land.

Imports come from :mod:`oh_my_harness.kb.services.paths`, the neutral shared layer,
to avoid a ``mcp/ → cli/`` sibling-adapter boundary violation.
"""

from __future__ import annotations

import os
from pathlib import Path

from oh_my_harness.kb.services.paths import DATA_ROOT_ENV, default_notes_root_for

UNIVERSE_ENV = "KB_UNIVERSE"
DEFAULT_UNIVERSE = "default"


def get_active_universe() -> str:
    """Return the active universe from ``$KB_UNIVERSE`` or the default."""
    return os.environ.get(UNIVERSE_ENV, DEFAULT_UNIVERSE)


def get_active_notes_root(universe: str | None = None) -> Path:
    """Return the notes-root directory for the active universe.

    Semantics align with the CLI: ``KB_NOTES_ROOT`` is treated as the
    **data root** (parent of all universes), not as a direct per-universe
    path.  The universe slug is always appended, so the same env var
    produces consistent paths whether the caller is ``omk`` or ``o-kb-mcp``.

    Examples
    --------
    ``KB_NOTES_ROOT=/data``, universe ``eng``  →  ``/data/eng``
    ``KB_NOTES_ROOT`` unset, universe ``eng``  →  ``~/oh-my-harness/eng``
    """
    target_universe = universe if universe is not None else get_active_universe()
    raw_override = os.environ.get(DATA_ROOT_ENV)
    if raw_override:
        return Path(raw_override).expanduser() / _slugify(target_universe)
    return default_notes_root_for(target_universe)


def _slugify(value: str) -> str:
    """Thin local import shim — avoids a top-level circular import."""
    from oh_my_harness.kb.core import slugify

    return slugify(value)
