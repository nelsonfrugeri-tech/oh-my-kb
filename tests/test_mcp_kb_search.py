from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from oh_my_kb.core import Note, NoteType
from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.mcp.tools.kb_search import handle_kb_search
from oh_my_kb.services import Indexer, SearchService
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
def search_service(store: QdrantStore, embedder: _StubEmbedder) -> SearchService:
    return SearchService(store=store, embedder=embedder)


def _note(summary: str, project: str = "oh-my-kb") -> Note:
    return Note(
        title=summary[:40] or "note",
        type=NoteType.DECISION,
        project=project,
        universe="engineering",
        created_at=datetime(2026, 5, 31, 14, 30, tzinfo=UTC),
        summary=summary,
    )


async def test_kb_search_formats_hits(
    indexer: Indexer, search_service: SearchService
) -> None:
    indexer.write_note(_note("Decisão sobre arquitetura."))
    indexer.write_note(_note("Outra decisão."))

    result = await handle_kb_search(
        search_service,
        "engineering",
        {"query": "Decisão sobre arquitetura.", "top_k": 2},
    )

    assert len(result) == 1
    text = result[0].text
    assert "kb_search:" in text
    assert "hit(s)" in text
    assert "id=" in text
    assert "score=" in text
    assert "title:" in text
    assert "summary:" in text


async def test_kb_search_no_hits_returns_friendly_message(
    indexer: Indexer, search_service: SearchService
) -> None:
    result = await handle_kb_search(
        search_service,
        "brand-new",
        {"query": "anything"},
    )
    assert "no notes match" in result[0].text
    assert "brand-new" in result[0].text


async def test_kb_search_project_filter(
    indexer: Indexer, search_service: SearchService
) -> None:
    indexer.write_note(_note("alpha-1", project="alpha"))
    indexer.write_note(_note("alpha-2", project="alpha"))
    indexer.write_note(_note("beta-1", project="beta"))

    result = await handle_kb_search(
        search_service,
        "engineering",
        {"query": "anything", "project": "alpha", "top_k": 10},
    )
    text = result[0].text
    assert "type/project: decision / alpha" in text
    assert "decision / beta" not in text


async def test_kb_search_respects_top_k(
    indexer: Indexer, search_service: SearchService
) -> None:
    for i in range(5):
        indexer.write_note(_note(f"summary {i}"))

    result = await handle_kb_search(
        search_service,
        "engineering",
        {"query": "anything", "top_k": 2},
    )
    text = result[0].text
    assert "2 hit(s)" in text


async def test_kb_search_friendly_message_includes_project_filter(
    indexer: Indexer, search_service: SearchService
) -> None:
    result = await handle_kb_search(
        search_service,
        "engineering",
        {"query": "anything", "project": "nope"},
    )
    assert "project=nope" in result[0].text
