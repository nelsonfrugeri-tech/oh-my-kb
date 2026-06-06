"""Tests for the ``kb_tree`` MCP tool handler.

Mirrors the pattern established in ``test_mcp_kb_search.py``: a stub embedder,
an in-memory QdrantStore, a real Indexer to seed data, and a real
NavigationService to prove the handler formats output correctly.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from oh_my_kb.core import Note, NoteType
from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.mcp.tools.kb_tree import handle_kb_tree
from oh_my_kb.services import Indexer, NavigationService
from oh_my_kb.storage import DENSE_DIM, IN_MEMORY, QdrantStore


class _StubEmbedder(Embedder):
    @property
    def dense_dim(self) -> int:
        return DENSE_DIM

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        results: list[EmbeddingResult] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            dense = [digest[i % 32] / 255.0 for i in range(DENSE_DIM)]
            sparse = SparseVector(
                indices=[int.from_bytes(digest[0:2], "little")],
                values=[1.0],
            )
            results.append(EmbeddingResult(dense=dense, sparse=sparse))
        return results


@pytest.fixture
def store() -> QdrantStore:
    return QdrantStore(IN_MEMORY)


@pytest.fixture
def embedder() -> _StubEmbedder:
    return _StubEmbedder()


@pytest.fixture
def indexer(store: QdrantStore, embedder: _StubEmbedder, tmp_path: Path) -> Indexer:
    return Indexer(store=store, embedder=embedder, notes_root=tmp_path)


@pytest.fixture
def navigation(store: QdrantStore, indexer: Indexer) -> NavigationService:
    return NavigationService(store=store, indexer=indexer)


def _note(
    *,
    title: str,
    project: str = "default",
    universe: str = "work",
    archived: bool = False,
    summary: str | None = None,
    note_id: UUID | None = None,
) -> Note:
    payload: dict[str, object] = {
        "title": title,
        "type": NoteType.DECISION,
        "project": project,
        "universe": universe,
        "created_at": datetime(2026, 5, 10, 14, 32, tzinfo=UTC),
        "summary": summary or f"summary of {title}",
        "archived": archived,
    }
    if note_id is not None:
        payload["id"] = note_id
    return Note(**payload)  # type: ignore[arg-type]


async def test_kb_tree_groups_by_project(
    indexer: Indexer, navigation: NavigationService
) -> None:
    """Two notes in different projects both appear, grouped under their section."""
    note_backend = _note(title="API Rate Limiting", project="backend")
    note_frontend = _note(title="Component Library", project="frontend")

    indexer.write_note(note_backend)
    indexer.write_note(note_frontend)

    result = await handle_kb_tree(navigation, "work", {})

    assert len(result) == 1
    text = result[0].text

    # Header
    assert "kb_tree:" in text
    assert "2 note(s)" in text
    assert "universe 'work'" in text

    # Both project sections present
    assert "=== backend ===" in text
    assert "=== frontend ===" in text

    # Both note ids and fields visible
    assert f"id={note_backend.id}" in text
    assert f"id={note_frontend.id}" in text
    assert "API Rate Limiting" in text
    assert "Component Library" in text
    assert "  title:" in text
    assert "  type:" in text
    assert "  summary:" in text


async def test_kb_tree_project_filter_restricts(
    indexer: Indexer, navigation: NavigationService
) -> None:
    """Project filter shows only matching notes; header contains (project=alpha)."""
    alpha1 = _note(title="alpha note 1", project="alpha")
    alpha2 = _note(title="alpha note 2", project="alpha")
    beta1 = _note(title="beta note 1", project="beta")

    indexer.write_note(alpha1)
    indexer.write_note(alpha2)
    indexer.write_note(beta1)

    result = await handle_kb_tree(navigation, "work", {"project": "alpha"})

    assert len(result) == 1
    text = result[0].text

    # Header must mention the filter
    assert "(project=alpha)" in text

    # Alpha notes visible
    assert f"id={alpha1.id}" in text
    assert f"id={alpha2.id}" in text
    assert "alpha note 1" in text
    assert "alpha note 2" in text

    # Beta must not appear
    assert f"id={beta1.id}" not in text
    assert "beta note 1" not in text
    assert "=== beta ===" not in text


async def test_kb_tree_empty_universe_returns_friendly_message(
    navigation: NavigationService,
) -> None:
    """Empty universe (no collection) returns a friendly message, not an error."""
    result = await handle_kb_tree(navigation, "brand-new-universe", {})

    assert len(result) == 1
    text = result[0].text
    assert "brand-new-universe" in text
    assert "no notes yet" in text
    assert "kb_write" in text


async def test_kb_tree_empty_project_filter_returns_friendly_message(
    indexer: Indexer, navigation: NavigationService
) -> None:
    """Universe has notes but project filter matches nothing — friendly message."""
    indexer.write_note(_note(title="some note", project="real-project"))

    result = await handle_kb_tree(navigation, "work", {"project": "infra"})

    assert len(result) == 1
    text = result[0].text
    assert "no notes found" in text
    assert "project=infra" in text
    assert "remove the project filter" in text


async def test_kb_tree_includes_archived_with_flag(
    indexer: Indexer, navigation: NavigationService
) -> None:
    """Archived note absent without flag; present with include_archived=True."""
    live = _note(title="live note", project="proj")
    archived = _note(title="archived note", project="proj", archived=True)

    indexer.write_note(live)
    indexer.write_note(archived)

    # Without flag — archived must not appear
    result_no_flag = await handle_kb_tree(navigation, "work", {})
    text_no_flag = result_no_flag[0].text
    assert "live note" in text_no_flag
    assert "archived note" not in text_no_flag

    # With flag — both appear
    result_with_flag = await handle_kb_tree(
        navigation, "work", {"include_archived": True}
    )
    text_with_flag = result_with_flag[0].text
    assert "live note" in text_with_flag
    assert "archived note" in text_with_flag
