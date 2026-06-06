"""Path conventions for the o-kb-client.

A single ``data_root`` (default ``~/oh-my-kb``) holds every universe as a
visible sub-directory named ``slug(universe)``. That keeps notes editable
and git-versionable without hiding them under a dotfile.

``KB_NOTES_ROOT`` is the **per-universe** override per the issue spec: when
set, it replaces the default ``data_root / slug(universe)`` for the universe
currently being acted on. Callers pass that resolved Path to :class:`Indexer`.

Implementation note: the actual helpers live in
:mod:`oh_my_kb.services.paths` (the neutral shared layer) so that the MCP
adapter can import them without creating a ``mcp/ → cli/`` boundary violation.
This module re-exports everything for backwards compatibility.
"""

from __future__ import annotations

# Re-export from the neutral services layer so external callers keep working.
from oh_my_kb.services.paths import (
    DATA_ROOT_ENV,
    DEFAULT_DATA_ROOT,
    default_notes_root_for,
    get_data_root,
)

__all__ = [
    "DATA_ROOT_ENV",
    "DEFAULT_DATA_ROOT",
    "default_notes_root_for",
    "get_data_root",
]
