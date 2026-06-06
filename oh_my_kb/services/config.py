"""Application-service configuration.

Centralizes filesystem-related environment variables so callers (CLI, MCP)
read the same source. Pure helper module — no I/O at import time.
"""

from __future__ import annotations

import os
from pathlib import Path

NOTES_ROOT_ENV = "KB_NOTES_ROOT"


def _default_notes_root() -> Path:
    """Return the default notes root based on the current ``$HOME``."""
    return Path.home() / "kb"


def get_notes_root() -> Path:
    """Return the notes-root directory from ``$KB_NOTES_ROOT`` or the default.

    ``Path.home()`` is evaluated lazily (inside the function) so tests that
    monkeypatch ``$HOME`` after import time see the correct value.
    """
    raw = os.environ.get(NOTES_ROOT_ENV)
    if raw:
        return Path(raw).expanduser()
    return _default_notes_root()
