"""Tests for the ``kb_expand`` MCP tool handler.

Mirrors the pattern established in ``test_mcp_kb_search.py``: a stub embedder,
an in-memory QdrantStore, a real Indexer to seed data, and a real
NavigationService to prove the handler formats output correctly.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from oh_my_kb.core import Note, NoteType
from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.mcp.tools.kb_expand import handle_kb_expand
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
    project: str = "backend",
    universe: str = "work",
    summary: str | None = None,
    body: str | None = None,
    links_out: list[UUID] | None = None,
    note_id: UUID | None = None,
) -> Note:
    payload: dict[str, object] = {
        "title": title,
        "type": NoteType.DECISION,
        "project": project,
        "universe": universe,
        "created_at": datetime(2026, 5, 10, 14, 32, tzinfo=UTC),
        "summary": summary or f"summary of {title}",
    }
    if body is not None:
        payload["body"] = body
    if links_out is not None:
        payload["links_out"] = links_out
    if note_id is not None:
        payload["id"] = note_id
    return Note(**payload)  # type: ignore[arg-type]


async def test_kb_expand_returns_note_with_body_and_links(
    indexer: Indexer, navigation: NavigationService
) -> None:
    """Expanding a note with links returns full body and resolved link metadata."""
    note_a = _note(
        title="Linked Note A",
        summary="summary of note A",
        note_id=uuid4(),
    )
    note_b = _note(
        title="Source Note B",
        summary="summary of note B",
        body="Full body of note B here.",
        links_out=[note_a.id],
        note_id=uuid4(),
    )

    indexer.write_note(note_a)
    indexer.write_note(note_b)

    result = await handle_kb_expand(navigation, "work", {"id": str(note_b.id)})

    assert len(result) == 1
    text = result[0].text

    # Header with note B's id
    assert f"kb_expand: note {note_b.id}" in text

    # Metadata fields
    assert "title:" in text
    assert "Source Note B" in text
    assert "type:" in text
    assert "project:" in text
    assert "created_at:" in text
    assert "summary:" in text

    # Body section
    assert "--- body ---" in text
    assert "Full body of note B here." in text
    assert "--- end body ---" in text

    # Links section with count
    assert "--- links out (1) ---" in text
    assert f"id={note_a.id}" in text
    assert "Linked Note A" in text
    assert "summary of note A" in text
    assert "--- end links ---" in text


async def test_kb_expand_no_links_returns_terminal_message(
    indexer: Indexer, navigation: NavigationService
) -> None:
    """A note with no outbound links shows the terminal note message."""
    note = _note(title="Terminal Note", body="Some body content.")
    indexer.write_note(note)

    result = await handle_kb_expand(navigation, "work", {"id": str(note.id)})

    assert len(result) == 1
    text = result[0].text

    # Body is present
    assert "--- body ---" in text
    assert "Some body content." in text

    # Terminal links section
    assert "--- links out ---" in text
    assert "no links out — terminal note." in text
    assert "--- end links ---" in text


async def test_kb_expand_unknown_id_returns_friendly_error(
    indexer: Indexer, navigation: NavigationService
) -> None:
    """A valid UUID that does not exist returns a friendly error, not a crash."""
    # Index something so the collection exists
    indexer.write_note(_note(title="anchor note"))

    non_existent_id = str(uuid4())
    result = await handle_kb_expand(navigation, "work", {"id": non_existent_id})

    assert len(result) == 1
    text = result[0].text
    assert "not found" in text
    assert non_existent_id in text
    assert "work" in text
    # Suggest navigation alternatives
    assert "kb_tree" in text or "kb_search" in text


async def test_kb_expand_invalid_uuid_returns_friendly_error(
    navigation: NavigationService,
) -> None:
    """A string that is not a UUID returns an invalid-input message without crashing."""
    result = await handle_kb_expand(navigation, "work", {"id": "not-a-uuid"})

    assert len(result) == 1
    text = result[0].text
    assert "invalid input" in text
    assert "UUID" in text
