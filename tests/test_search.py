from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from oh_my_kb.core import Note, NoteType
from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.services import (
    Indexer,
    SearchResult,
    SearchService,
)
from oh_my_kb.storage import DENSE_DIM, IN_MEMORY, QdrantStore


class _StubEmbedder(Embedder):
    """Deterministic stand-in for the real embedder.

    Equal text -> equal vector; different text -> different vector. Same
    routine used by the indexer tests so a search query that exactly matches
    an indexed summary will yield the highest similarity for that note.
    """

    @property
    def dense_dim(self) -> int:
        return DENSE_DIM

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        results: list[EmbeddingResult] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            dense = [digest[i % 32] / 255.0 for i in range(DENSE_DIM)]
            sparse = SparseVector(
                indices=[
                    int.from_bytes(digest[0:2], "little"),
                    int.from_bytes(digest[2:4], "little"),
                ],
                values=[0.5, 0.3],
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


def _note(
    *,
    summary: str,
    project: str = "oh-my-kb",
    universe: str = "engineering",
    archived: bool = False,
    title: str | None = None,
) -> Note:
    return Note(
        title=title or summary.split(".")[0][:80],
        type=NoteType.DECISION,
        project=project,
        universe=universe,
        created_at=datetime(2026, 5, 31, 14, 30, tzinfo=UTC),
        summary=summary,
        archived=archived,
    )


# --- empty state -------------------------------------------------------


def test_missing_collection_returns_empty_list(search_service: SearchService) -> None:
    assert search_service.search("anything", universe="brand-new") == []


def test_existing_but_empty_collection_returns_empty_list(
    search_service: SearchService, store: QdrantStore, indexer: Indexer
) -> None:
    from oh_my_kb.services.indexer import collection_name_for

    store.ensure_collection(collection_name_for("engineering"))
    assert search_service.search("anything", universe="engineering") == []


# --- happy path --------------------------------------------------------


def test_returns_search_result_with_payload_fields(
    indexer: Indexer, search_service: SearchService
) -> None:
    note = _note(summary="Decisão sobre arquitetura de tools no MCP.")
    indexer.write_note(note)

    results = search_service.search(note.summary, universe=note.universe, top_k=5)

    assert len(results) == 1
    hit = results[0]
    assert isinstance(hit, SearchResult)
    assert hit.id == str(note.id)
    assert hit.title == note.title
    assert hit.summary == note.summary
    assert hit.type == note.type.value
    assert hit.project == note.project
    assert hit.archived == note.archived
    assert hit.created_at == note.created_at
    assert Path(hit.path).is_file()
    assert hit.score > 0.0


def test_respects_top_k(indexer: Indexer, search_service: SearchService) -> None:
    summaries = [f"Decisão número {i} sobre o módulo X." for i in range(7)]
    for s in summaries:
        indexer.write_note(_note(summary=s))

    results = search_service.search("qualquer coisa", universe="engineering", top_k=3)
    assert len(results) == 3


def test_results_are_sorted_by_score_desc(
    indexer: Indexer, search_service: SearchService
) -> None:
    for s in ("alpha", "beta", "gamma"):
        indexer.write_note(_note(summary=s))

    results = search_service.search("alpha", universe="engineering", top_k=3)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


# --- filters -----------------------------------------------------------


def test_project_filter_restricts_results(
    indexer: Indexer, search_service: SearchService
) -> None:
    indexer.write_note(_note(summary="A1", project="alpha"))
    indexer.write_note(_note(summary="A2", project="alpha"))
    indexer.write_note(_note(summary="B1", project="beta"))

    alpha = search_service.search("anything", universe="engineering", project="alpha", top_k=10)
    beta = search_service.search("anything", universe="engineering", project="beta", top_k=10)

    assert {r.project for r in alpha} == {"alpha"}
    assert len(alpha) == 2
    assert {r.project for r in beta} == {"beta"}
    assert len(beta) == 1


def test_archived_excluded_by_default(
    indexer: Indexer, search_service: SearchService
) -> None:
    indexer.write_note(_note(summary="ativa"))
    indexer.write_note(_note(summary="arquivada", archived=True))

    results = search_service.search("anything", universe="engineering", top_k=10)
    assert {r.summary for r in results} == {"ativa"}


def test_include_archived_returns_both(
    indexer: Indexer, search_service: SearchService
) -> None:
    indexer.write_note(_note(summary="ativa"))
    indexer.write_note(_note(summary="arquivada", archived=True))

    results = search_service.search(
        "anything", universe="engineering", top_k=10, include_archived=True
    )
    assert {r.summary for r in results} == {"ativa", "arquivada"}


def test_filter_combination_archived_and_project(
    indexer: Indexer, search_service: SearchService
) -> None:
    indexer.write_note(_note(summary="alpha-ativa", project="alpha"))
    indexer.write_note(_note(summary="alpha-arquivada", project="alpha", archived=True))
    indexer.write_note(_note(summary="beta-ativa", project="beta"))

    results = search_service.search(
        "anything", universe="engineering", project="alpha", top_k=10
    )
    assert {r.summary for r in results} == {"alpha-ativa"}


def test_project_filter_with_no_match_returns_empty(
    indexer: Indexer, search_service: SearchService
) -> None:
    indexer.write_note(_note(summary="A", project="alpha"))
    results = search_service.search(
        "anything", universe="engineering", project="unknown", top_k=5
    )
    assert results == []
