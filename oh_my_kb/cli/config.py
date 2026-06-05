"""Multiverse configuration for the o-kb-client.

Persists the list of universes (each with ``name``, ``notes_root``,
``collection``) plus the active universe in a TOML file under
``~/.config/oh-my-kb/config.toml``. The directory is XDG-style hidden
because it's machine config — note **data** lives in plain sight under
``~/oh-my-kb/`` (see :mod:`oh_my_kb.cli.paths`).

The collection name is **never** computed locally — it is delegated to
:func:`oh_my_kb.services.collection_name_for` so the CLI and the indexer
never disagree.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

import tomli_w

from oh_my_kb.services import collection_name_for

CONFIG_DIR_ENV = "OMK_CONFIG_DIR"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "oh-my-kb"
CONFIG_FILE_NAME = "config.toml"


class UniverseAlreadyExistsError(ValueError):
    """Raised when adding a universe whose name already exists in the config."""


class UniverseNotFoundError(LookupError):
    """Raised when activating or referencing a universe that isn't in the config."""


@dataclass(frozen=True, slots=True)
class Universe:
    name: str
    notes_root: Path
    collection: str


@dataclass(frozen=True, slots=True)
class CLIConfig:
    universes: list[Universe] = field(default_factory=list)
    active: str | None = None

    def get(self, name: str) -> Universe | None:
        for u in self.universes:
            if u.name == name:
                return u
        return None

    def has(self, name: str) -> bool:
        return self.get(name) is not None


def config_dir() -> Path:
    """Return the directory holding ``config.toml``.

    Honors the ``OMK_CONFIG_DIR`` env var (used by tests); falls back to
    ``~/.config/oh-my-kb``.
    """
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return DEFAULT_CONFIG_DIR


def config_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


def load_config() -> CLIConfig:
    """Read the config file, returning an empty :class:`CLIConfig` if absent."""
    path = config_path()
    if not path.exists():
        return CLIConfig()
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    universes = [
        Universe(
            name=str(u["name"]),
            notes_root=Path(str(u["notes_root"])),
            collection=str(u["collection"]),
        )
        for u in raw.get("universes", [])
    ]
    active = raw.get("active")
    return CLIConfig(universes=universes, active=active)


def save_config(cfg: CLIConfig) -> Path:
    """Persist ``cfg`` to ``config_path``, creating the directory if missing."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {
        "universes": [
            {
                "name": u.name,
                "notes_root": str(u.notes_root),
                "collection": u.collection,
            }
            for u in cfg.universes
        ],
    }
    if cfg.active is not None:
        data["active"] = cfg.active
    with path.open("wb") as fh:
        tomli_w.dump(data, fh)
    return path


def add_universe(cfg: CLIConfig, *, name: str, notes_root: Path) -> CLIConfig:
    """Return a new ``CLIConfig`` with ``name`` added.

    Raises :class:`UniverseAlreadyExistsError` if a universe with that name
    already exists. The collection is derived from
    :func:`oh_my_kb.services.collection_name_for`.
    """
    if cfg.has(name):
        raise UniverseAlreadyExistsError(f"universe '{name}' already exists")
    new_universe = Universe(
        name=name,
        notes_root=notes_root,
        collection=collection_name_for(name),
    )
    return replace(cfg, universes=[*cfg.universes, new_universe])


def set_active(cfg: CLIConfig, name: str) -> CLIConfig:
    """Return a new ``CLIConfig`` whose ``active`` is ``name``.

    Raises :class:`UniverseNotFoundError` if ``name`` is not in the config.
    """
    if not cfg.has(name):
        raise UniverseNotFoundError(f"universe '{name}' is not configured")
    return replace(cfg, active=name)
