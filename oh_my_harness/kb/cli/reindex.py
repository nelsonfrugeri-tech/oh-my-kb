"""ReindexRunner — testable orchestrator for ``omk reindex``.

Mirrors the pattern established by :class:`oh_my_harness.kb.cli.installer.Installer`:
all external dependencies arrive via constructor-injected callables so the
whole flow can be exercised in unit tests without touching Docker, the
filesystem, or the real bge-m3 model.

:class:`NoActiveUniverseError` is defined here rather than imported from
:mod:`oh_my_harness.kb.agents.bootstrap` to keep the CLI reindex logic self-contained
and avoid a cross-module dependency for a simple sentinel exception.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from oh_my_harness.kb.cli.config import CLIConfig, UniverseNotFoundError, load_config
from oh_my_harness.kb.embedding import Embedder
from oh_my_harness.kb.services import Indexer, ReindexReport, reindex_universe
from oh_my_harness.kb.storage import QdrantStore, get_qdrant_url

StoreFactory = Callable[[str], QdrantStore]
EmbedderFactory = Callable[[], Embedder]
QdrantUrlResolver = Callable[[], str]
ConfigLoader = Callable[[], CLIConfig]


class NoActiveUniverseError(RuntimeError):
    """Raised when no active universe is configured and none was specified."""


def _default_store_factory(url: str) -> QdrantStore:
    return QdrantStore(url)


def _default_embedder_factory() -> Embedder:
    from oh_my_harness.kb.embedding import BGEM3Embedder

    return BGEM3Embedder()


@dataclass
class ReindexRunner:
    """Orchestrator for the ``omk reindex`` command.

    All external side-effects (store creation, embedder loading, URL resolution)
    are reachable through constructor-injected callables so tests can drive the
    whole flow with fakes.

    Parameters
    ----------
    store_factory:
        Callable that accepts a Qdrant URL and returns a :class:`QdrantStore`.
    embedder_factory:
        Callable that returns an :class:`Embedder` instance.
    qdrant_url_resolver:
        Callable that returns the Qdrant URL string.
    config_loader:
        Callable that returns the current :class:`CLIConfig`.  Defaults to
        :func:`oh_my_harness.kb.cli.config.load_config` so production use is seamless.
    """

    store_factory: StoreFactory = field(default=_default_store_factory)
    embedder_factory: EmbedderFactory = field(default=_default_embedder_factory)
    qdrant_url_resolver: QdrantUrlResolver = field(default=get_qdrant_url)
    config_loader: ConfigLoader = field(default=load_config)

    def run(self, universe: str | None = None) -> ReindexReport:
        """Reindex the specified (or active) universe.

        Parameters
        ----------
        universe:
            Name of the universe to reindex.  When ``None`` the active universe
            from the CLI config is used.

        Raises
        ------
        NoActiveUniverseError
            If ``universe`` is ``None`` and no active universe is configured.
        UniverseNotFoundError
            If the resolved universe name is not in the config.
        """
        cfg = self.config_loader()

        resolved_name = universe if universe is not None else cfg.active
        if resolved_name is None:
            raise NoActiveUniverseError(
                "no active universe — run `omk install` first or pass --universe"
            )

        universe_cfg = cfg.get(resolved_name)
        if universe_cfg is None:
            raise UniverseNotFoundError(f"universe '{resolved_name}' not found in config")

        url = self.qdrant_url_resolver()
        store = self.store_factory(url)
        embedder = self.embedder_factory()
        indexer = Indexer(store=store, embedder=embedder, notes_root=universe_cfg.notes_root)

        return reindex_universe(
            indexer=indexer,
            universe=resolved_name,
            notes_root=universe_cfg.notes_root,
        )
