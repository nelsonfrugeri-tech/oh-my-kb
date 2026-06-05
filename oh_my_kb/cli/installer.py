"""Provisioning orchestrator for ``omk install``.

Brings up the local Qdrant, makes sure the bge-m3 model is on disk, and
guarantees a ``default`` universe is registered and active. All steps are
idempotent — re-running ``omk install`` on a healthy machine is a no-op
that just reprints the current state.

Every external side-effect (subprocess, network, model load) is reachable
through a constructor-injected callable so tests can drive the whole flow
with fakes and assert ordering, idempotency, and error paths without ever
calling Docker or HuggingFace.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from oh_my_kb.cli.config import (
    CLIConfig,
    add_universe,
    config_path,
    load_config,
    save_config,
    set_active,
)
from oh_my_kb.cli.paths import default_notes_root_for
from oh_my_kb.embedding import BGEM3Embedder, Embedder
from oh_my_kb.services import collection_name_for
from oh_my_kb.storage import QdrantStore, get_qdrant_url

DEFAULT_UNIVERSE = "default"
HEALTHCHECK_TIMEOUT_SECONDS = 60
HEALTHCHECK_INTERVAL_SECONDS = 1.0

DockerRunner = Callable[[list[str]], None]
StoreFactory = Callable[[str], QdrantStore]
EmbedderFactory = Callable[[], Embedder]
Sleeper = Callable[[float], None]


class QdrantUnreachableError(RuntimeError):
    """Raised when Qdrant doesn't become healthy within the timeout."""


def _default_docker_runner(argv: list[str]) -> None:
    subprocess.run(argv, check=True)


def _default_store_factory(url: str) -> QdrantStore:
    return QdrantStore(url)


def _default_embedder_factory() -> Embedder:
    # Construction is cheap (lazy load) — touching ``embed_text`` triggers
    # the actual HuggingFace download.
    embedder = BGEM3Embedder()
    embedder.embed_text("warm-up")
    return embedder


@dataclass(frozen=True, slots=True)
class InstallReport:
    qdrant_url: str
    universe: str
    notes_root: Path
    collection: str
    config_file: Path
    actions: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Installer:
    qdrant_url: str = field(default_factory=get_qdrant_url)
    docker_runner: DockerRunner = field(default=_default_docker_runner)
    store_factory: StoreFactory = field(default=_default_store_factory)
    embedder_factory: EmbedderFactory = field(default=_default_embedder_factory)
    sleeper: Sleeper = field(default=time.sleep)
    healthcheck_timeout: float = HEALTHCHECK_TIMEOUT_SECONDS
    healthcheck_interval: float = HEALTHCHECK_INTERVAL_SECONDS
    default_universe: str = DEFAULT_UNIVERSE

    def run(self) -> InstallReport:
        actions: list[str] = []
        store = self._ensure_qdrant(actions)
        self._ensure_embedder(actions)
        _cfg, universe_notes_root = self._ensure_default_universe(store, actions)
        return InstallReport(
            qdrant_url=self.qdrant_url,
            universe=self.default_universe,
            notes_root=universe_notes_root,
            collection=collection_name_for(self.default_universe),
            config_file=config_path(),
            actions=actions,
        )

    def _ensure_qdrant(self, actions: list[str]) -> QdrantStore:
        store = self.store_factory(self.qdrant_url)
        if store.healthcheck():
            actions.append(f"qdrant already healthy at {self.qdrant_url}")
            return store

        actions.append("starting qdrant via docker compose")
        self.docker_runner(shlex.split("docker compose up -d"))

        deadline = time.monotonic() + self.healthcheck_timeout
        while time.monotonic() < deadline:
            if store.healthcheck():
                actions.append(f"qdrant healthy at {self.qdrant_url}")
                return store
            self.sleeper(self.healthcheck_interval)
        raise QdrantUnreachableError(
            f"qdrant at {self.qdrant_url} did not become healthy within "
            f"{self.healthcheck_timeout:.0f}s"
        )

    def _ensure_embedder(self, actions: list[str]) -> Embedder:
        embedder = self.embedder_factory()
        actions.append("bge-m3 model ready (cached after first download)")
        return embedder

    def _ensure_default_universe(
        self, store: QdrantStore, actions: list[str]
    ) -> tuple[CLIConfig, Path]:
        cfg = load_config()
        notes_root = default_notes_root_for(self.default_universe)
        notes_root.mkdir(parents=True, exist_ok=True)

        if not cfg.has(self.default_universe):
            cfg = add_universe(cfg, name=self.default_universe, notes_root=notes_root)
            actions.append(f"registered universe '{self.default_universe}' in config")
        else:
            actions.append(f"universe '{self.default_universe}' already in config")

        collection = collection_name_for(self.default_universe)
        if store.collection_exists(collection):
            actions.append(f"collection '{collection}' already exists")
        else:
            store.ensure_collection(collection)
            actions.append(f"created collection '{collection}'")

        if cfg.active != self.default_universe:
            cfg = set_active(cfg, self.default_universe)
            actions.append(f"set '{self.default_universe}' as active universe")
        else:
            actions.append(f"'{self.default_universe}' already active")

        save_config(cfg)
        return cfg, notes_root
