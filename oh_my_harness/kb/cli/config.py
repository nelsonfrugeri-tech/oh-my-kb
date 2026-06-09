"""Multiverse configuration for the o-kb-client.

Persists the list of universes (each with ``name``, ``notes_root``,
``collection``) plus the active universe in a TOML file under
``~/.config/oh-my-harness/config.toml``. The directory is XDG-style hidden
because it's machine config — note **data** lives in plain sight under
``~/oh-my-harness/`` (see :mod:`oh_my_harness.kb.cli.paths`).

The collection name is **never** computed locally — it is delegated to
:func:`oh_my_harness.kb.services.collection_name_for` so the CLI and the indexer
never disagree.

Two schemas coexist in the same TOML file using disjoint top-level sections:
- :class:`CLIConfig` — ``universes`` + ``active`` (original schema).
- :class:`OmkConfig` — ``[core]``, ``[qdrant]``, ``[harness]`` sections.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

import tomli_w

from oh_my_harness.kb.services import collection_name_for

CONFIG_DIR_ENV = "OMH_CONFIG_DIR"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "oh-my-harness"
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

    Honors the ``OMH_CONFIG_DIR`` env var (used by tests); falls back to
    ``~/.config/oh-my-harness``.
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
    """Persist ``cfg`` to ``config_path``, creating the directory if missing.

    Reads the existing file first so that :class:`OmkConfig` sections
    (``[core]``, ``[qdrant]``, ``[harness]``) are not overwritten.
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Preserve any existing sections (e.g. OmkConfig's [core]/[qdrant]/[harness])
    existing: dict[str, object] = {}
    if path.exists():
        with path.open("rb") as fh:
            existing = dict(tomllib.load(fh))

    existing["universes"] = [
        {
            "name": u.name,
            "notes_root": str(u.notes_root),
            "collection": u.collection,
        }
        for u in cfg.universes
    ]
    if cfg.active is not None:
        existing["active"] = cfg.active
    elif "active" in existing:
        del existing["active"]

    with path.open("wb") as fh:
        tomli_w.dump(existing, fh)
    return path


def add_universe(cfg: CLIConfig, *, name: str, notes_root: Path) -> CLIConfig:
    """Return a new ``CLIConfig`` with ``name`` added.

    Raises :class:`UniverseAlreadyExistsError` if a universe with that name
    already exists. The collection is derived from
    :func:`oh_my_harness.kb.services.collection_name_for`.
    """
    if cfg.has(name):
        raise UniverseAlreadyExistsError(f"knowledge base '{name}' already exists")
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
        raise UniverseNotFoundError(f"knowledge base '{name}' is not configured")
    return replace(cfg, active=name)


# ---------------------------------------------------------------------------
# OmkConfig — extended install configuration (disjoint TOML sections)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OmkCoreConfig:
    """``[core]`` section of ``config.toml``."""

    notes_root: Path = field(default_factory=lambda: Path.home() / "oh-my-harness")
    default_universe: str = "default"
    models_cache: Path = field(
        default_factory=lambda: Path.home() / ".cache" / "oh-my-harness" / "models"
    )


@dataclass(frozen=True, slots=True)
class OmkQdrantConfig:
    """``[qdrant]`` section of ``config.toml``."""

    port: int = 6333
    container_name: str = "oh-my-harness-qdrant"


@dataclass(frozen=True, slots=True)
class OmkHarnessConfig:
    """``[harness]`` section of ``config.toml``."""

    active: str = "claude-code"


@dataclass(frozen=True, slots=True)
class OmkConfig:
    """Extended installation configuration — coexists with :class:`CLIConfig`.

    Stored under the ``[core]``, ``[qdrant]``, and ``[harness]`` sections of
    ``~/.config/oh-my-harness/config.toml``, which are disjoint from the
    ``universes`` / ``active`` keys used by :class:`CLIConfig`.
    """

    core: OmkCoreConfig = field(default_factory=OmkCoreConfig)
    qdrant: OmkQdrantConfig = field(default_factory=OmkQdrantConfig)
    harness: OmkHarnessConfig = field(default_factory=OmkHarnessConfig)


def omk_config_path() -> Path:
    """Return the path to the config file (same as :func:`config_path`)."""
    return config_path()


def load_omk_config() -> OmkConfig:
    """Load :class:`OmkConfig` from ``config.toml``.

    Returns defaults if the file is absent or if the relevant sections
    are not yet present (e.g. on a fresh install or upgrade from an older
    version).
    """
    path = omk_config_path()
    if not path.exists():
        return OmkConfig()

    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    core_raw = raw.get("core", {})
    qdrant_raw = raw.get("qdrant", {})
    harness_raw = raw.get("harness", {})

    _defaults = OmkCoreConfig()
    core = OmkCoreConfig(
        notes_root=(
            Path(str(core_raw["notes_root"])) if "notes_root" in core_raw else _defaults.notes_root
        ),
        default_universe=str(core_raw.get("default_universe", _defaults.default_universe)),
        models_cache=(
            Path(str(core_raw["models_cache"]))
            if "models_cache" in core_raw
            else _defaults.models_cache
        ),
    )
    qdrant = OmkQdrantConfig(
        port=int(qdrant_raw.get("port", OmkQdrantConfig().port)),
        container_name=str(qdrant_raw.get("container_name", OmkQdrantConfig().container_name)),
    )
    harness = OmkHarnessConfig(
        active=str(harness_raw.get("active", OmkHarnessConfig().active)),
    )
    return OmkConfig(core=core, qdrant=qdrant, harness=harness)


def save_omk_config(cfg: OmkConfig) -> Path:
    """Persist :class:`OmkConfig` to ``config.toml``.

    Reads the existing file first and merges the new sections in, so that
    :class:`CLIConfig` data (``universes`` / ``active``) is preserved.
    """
    path = omk_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing data to preserve CLIConfig sections
    existing: dict[str, object] = {}
    if path.exists():
        with path.open("rb") as fh:
            existing = dict(tomllib.load(fh))

    # Merge in the new OmkConfig sections (overwrite only our sections)
    existing["core"] = {
        "notes_root": str(cfg.core.notes_root),
        "default_universe": cfg.core.default_universe,
        "models_cache": str(cfg.core.models_cache),
    }
    existing["qdrant"] = {
        "port": cfg.qdrant.port,
        "container_name": cfg.qdrant.container_name,
    }
    existing["harness"] = {
        "active": cfg.harness.active,
    }

    with path.open("wb") as fh:
        tomli_w.dump(existing, fh)
    return path
