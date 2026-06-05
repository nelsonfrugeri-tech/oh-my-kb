"""Path conventions for the o-kb-client.

A single ``data_root`` (default ``~/oh-my-kb``) holds every universe as a
visible sub-directory named ``slug(universe)``. That keeps notes editable
and git-versionable without hiding them under a dotfile.

``KB_NOTES_ROOT`` is the **per-universe** override per the issue spec: when
set, it replaces the default ``data_root / slug(universe)`` for the universe
currently being acted on. Callers pass that resolved Path to :class:`Indexer`.
"""

from __future__ import annotations

import os
from pathlib import Path

from oh_my_kb.core import slugify

DATA_ROOT_ENV = "KB_NOTES_ROOT"
DEFAULT_DATA_ROOT = Path.home() / "oh-my-kb"


def get_data_root() -> Path:
    """Return the data root (parent of every universe directory)."""
    raw = os.environ.get(DATA_ROOT_ENV)
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_DATA_ROOT


def default_notes_root_for(universe: str, data_root: Path | None = None) -> Path:
    """Return the default notes-root path for ``universe``.

    ``data_root / slug(universe)``. ``data_root`` defaults to
    :func:`get_data_root` so the caller doesn't have to thread it through.
    """
    base = data_root if data_root is not None else get_data_root()
    return base / slugify(universe)
