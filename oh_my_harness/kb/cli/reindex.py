"""ReindexRunner — testable orchestrator for ``omh reindex``.

Mirrors the pattern established by :class:`oh_my_harness.kb.cli.installer.Installer`:
all external dependencies arrive via constructor-injected callables so the
whole flow can be exercised in unit tests without touching Docker, the
filesystem, or the real bge-m3 model.

:class:`NoActiveKbError` is defined here rather than imported from
:mod:`oh_my_harness.kb.agents.bootstrap` to keep the CLI reindex logic self-contained
and avoid a cross-module dependency for a simple sentinel exception.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from oh_my_harness.kb.cli.config import CLIConfig, KbNotFoundError, load_config
from oh_my_harness.kb.embedding import Embedder
from oh_my_harness.kb.services import Indexer, ReindexReport, reindex_universe
from oh_my_harness.kb.storage import QdrantStore, get_qdrant_url

# Backward-compatible alias — KbNotFoundError is the canonical name.
UniverseNotFoundError = KbNotFoundError  # backward-compatible alias

StoreFactory = Callable[[str], QdrantStore]
EmbedderFactory = Callable[[], Embedder]
QdrantUrlResolver = Callable[[], str]
ConfigLoader = Callable[[], CLIConfig]


class NoActiveKbError(RuntimeError):
    """Raised when no active knowledge base is configured and none was specified."""


# Backward-compatible alias.
NoActiveUniverseError = NoActiveKbError  # backward-compatible alias


def _default_store_factory(url: str) -> QdrantStore:
    return QdrantStore(url)


def _default_embedder_factory() -> Embedder:
    from oh_my_harness.kb.embedding import BGEM3Embedder

    return BGEM3Embedder()


@dataclass
class ReindexRunner:
    """Orchestrator for the ``omh reindex`` command.

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

    def run(self, kb_name: str | None = None) -> ReindexReport:
        """Reindex the specified (or active) knowledge base.

        Parameters
        ----------
        kb_name:
            Name of the knowledge base to reindex.  When ``None`` the active
            knowledge base from the CLI config is used.

        Raises
        ------
        NoActiveKbError
            If ``kb_name`` is ``None`` and no active knowledge base is configured.
        KbNotFoundError
            If the resolved knowledge base name is not in the config.
        """
        cfg = self.config_loader()

        resolved_name = kb_name if kb_name is not None else cfg.active
        if resolved_name is None:
            raise NoActiveKbError(
                "no active knowledge base — run `omh install` first or pass --universe"
            )

        kb_cfg = cfg.get(resolved_name)
        if kb_cfg is None:
            raise KbNotFoundError(f"knowledge base '{resolved_name}' not found in config")

        url = self.qdrant_url_resolver()
        store = self.store_factory(url)
        embedder = self.embedder_factory()
        indexer = Indexer(store=store, embedder=embedder, notes_root=kb_cfg.notes_root)

        return reindex_universe(
            indexer=indexer,
            universe=resolved_name,
            notes_root=kb_cfg.notes_root,
        )
