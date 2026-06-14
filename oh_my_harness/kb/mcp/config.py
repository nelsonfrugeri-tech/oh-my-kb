"""MCP server configuration.

A single ``KB_NAME`` env var binds the running server to one knowledge base;
the active notes_root is derived from it via the same conventions the CLI
uses (:func:`oh_my_harness.kb.services.paths.default_notes_root_for`). Future
iterations may read the active knowledge base from the TOML config written by
``omk`` — this module is the choke-point where that change will land.

Imports come from :mod:`oh_my_harness.kb.services.paths`, the neutral shared layer,
to avoid a ``mcp/ → cli/`` sibling-adapter boundary violation.

Migration note
--------------
``KB_UNIVERSE`` is accepted as a fallback when ``KB_NAME`` is not set, to support
users who have the old env var configured. The fallback is silent — no warning is
printed, because MCP servers may not have a visible stderr in all harnesses.
"""

from __future__ import annotations

import os
from pathlib import Path

from oh_my_harness.kb.services.paths import DATA_ROOT_ENV, default_notes_root_for

# Current env var name.
KB_NAME_ENV = "KB_NAME"
# Legacy fallback — read if KB_NAME is absent.
_KB_UNIVERSE_LEGACY_ENV = "KB_UNIVERSE"
DEFAULT_KB = "default"

# Keep old names as aliases so existing imports (e.g. tests) keep working.
UNIVERSE_ENV = KB_NAME_ENV
DEFAULT_UNIVERSE = DEFAULT_KB


def get_active_kb() -> str:
    """Return the active knowledge base from ``$KB_NAME`` (or legacy ``$KB_UNIVERSE``)."""
    value = os.environ.get(KB_NAME_ENV)
    if value:
        return value
    # Fallback for users who still have KB_UNIVERSE set.
    legacy = os.environ.get(_KB_UNIVERSE_LEGACY_ENV)
    if legacy:
        return legacy
    return DEFAULT_KB


# Backward-compatible alias — existing call sites keep working unchanged.
def get_active_universe() -> str:
    """Deprecated alias for :func:`get_active_kb`."""
    return get_active_kb()


def get_active_notes_root(kb_name: str | None = None) -> Path:
    """Return the notes-root directory for the active knowledge base.

    Semantics align with the CLI: ``KB_NOTES_ROOT`` is treated as the
    **data root** (parent of all knowledge bases), not as a direct per-kb
    path.  The kb slug is always appended, so the same env var
    produces consistent paths whether the caller is ``omk`` or ``o-kb-mcp``.

    Examples
    --------
    ``KB_NOTES_ROOT=/data``, kb ``eng``  →  ``/data/eng``
    ``KB_NOTES_ROOT`` unset, kb ``eng``  →  ``~/oh-my-harness/eng``
    """
    target_kb = kb_name if kb_name is not None else get_active_kb()
    raw_override = os.environ.get(DATA_ROOT_ENV)
    if raw_override:
        return Path(raw_override).expanduser() / _slugify(target_kb)
    return default_notes_root_for(target_kb)


def _slugify(value: str) -> str:
    """Thin local import shim — avoids a top-level circular import."""
    from oh_my_harness.kb.core import slugify

    return slugify(value)
