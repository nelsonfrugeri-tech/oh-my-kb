"""Application-service configuration.

Centralizes filesystem-related environment variables so callers (CLI, MCP)
read the same source. Pure helper module — no I/O at import time.
"""

from __future__ import annotations

import os
from pathlib import Path

NOTES_ROOT_ENV = "KB_NOTES_ROOT"
DEFAULT_NOTES_ROOT = Path.home() / "kb"


def get_notes_root() -> Path:
    """Return the notes-root directory from ``$KB_NOTES_ROOT`` or the default."""
    raw = os.environ.get(NOTES_ROOT_ENV)
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_NOTES_ROOT
