"""MCP server configuration.

A single ``KB_UNIVERSE`` env var binds the running server to one universe;
the active notes_root is derived from it via the same conventions the CLI
uses (:func:`oh_my_kb.cli.paths.default_notes_root_for`). Future iterations
may read the active universe from the TOML config written by ``omk`` — this
module is the choke-point where that change will land.
"""

from __future__ import annotations

import os
from pathlib import Path

from oh_my_kb.cli.paths import DATA_ROOT_ENV, default_notes_root_for

UNIVERSE_ENV = "KB_UNIVERSE"
DEFAULT_UNIVERSE = "default"


def get_active_universe() -> str:
    """Return the active universe from ``$KB_UNIVERSE`` or the default."""
    return os.environ.get(UNIVERSE_ENV, DEFAULT_UNIVERSE)


def get_active_notes_root(universe: str | None = None) -> Path:
    """Return the notes-root directory for the active universe.

    If ``KB_NOTES_ROOT`` is set it wins (single-value override applies to
    whichever universe the server is bound to); otherwise the default
    ``~/oh-my-kb/<slug(universe)>`` layout is used.
    """
    target_universe = universe if universe is not None else get_active_universe()
    raw_override = os.environ.get(DATA_ROOT_ENV)
    if raw_override:
        return Path(raw_override).expanduser()
    return default_notes_root_for(target_universe)
