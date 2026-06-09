"""Shared pytest fixtures for the oh-my-harness test suite.

Shared helper classes and functions (``StubEmbedder``, ``make_note``) live in
``tests/_helpers.py`` so that test modules can import them directly by name.
This file wires ``StubEmbedder`` into pytest's fixture machinery.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from _helpers import StubEmbedder

from oh_my_harness.kb.services import Indexer, NavigationService, SearchService
from oh_my_harness.kb.storage import IN_MEMORY, QdrantStore

# ---------------------------------------------------------------------------
# Common pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> QdrantStore:
    """Fresh in-memory QdrantStore for each test."""
    return QdrantStore(IN_MEMORY)


@pytest.fixture
def embedder() -> StubEmbedder:
    """Shared StubEmbedder instance for each test."""
    return StubEmbedder()


@pytest.fixture
def indexer(store: QdrantStore, embedder: StubEmbedder, tmp_path: Path) -> Indexer:
    """Indexer wired to the in-memory store and stub embedder."""
    return Indexer(store=store, embedder=embedder, notes_root=tmp_path)


@pytest.fixture
def search_service(store: QdrantStore, embedder: StubEmbedder) -> SearchService:
    """SearchService wired to the in-memory store and stub embedder."""
    return SearchService(store=store, embedder=embedder)


@pytest.fixture
def navigation_service(store: QdrantStore, indexer: Indexer) -> NavigationService:
    """NavigationService wired to the in-memory store and indexer."""
    return NavigationService(store=store, indexer=indexer)


# ---------------------------------------------------------------------------
# Resource CLI fixtures (used by tests/test_cli_resource_*.py)
# ---------------------------------------------------------------------------

_MOCK_CONTENT_TEMPLATE = (
    "<!-- content_version: 1 | locale: {locale} | updated: 2026-01-01 -->\n# Mock"
)


@pytest.fixture
def fake_claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated ``~/.claude/`` directory under ``tmp_path``.

    Sets the ``HOME`` environment variable to ``tmp_path`` so that
    ``Path("~/.claude/...").expanduser()`` resolves to ``tmp_path / ".claude" / ...``.
    Scoped to the test function — does not affect other tests.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    return tmp_path


@pytest.fixture
def mock_read_resource(monkeypatch: pytest.MonkeyPatch) -> Callable[[str, str], str]:
    """Monkeypatched ``read_scribe_resource`` that returns predictable content."""

    def _read(uri: str, locale: str = "pt-BR") -> str:
        return _MOCK_CONTENT_TEMPLATE.format(locale=locale)

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _read)
    return _read
