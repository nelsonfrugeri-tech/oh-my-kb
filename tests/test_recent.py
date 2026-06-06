"""Fast unit tests for :class:`~oh_my_kb.services.recent.RecentService`.

Uses ``QdrantStore(':memory:')`` and a deterministic stub embedder.  Real bge-m3
integration lives in ``test_recent_integration.py`` (``@pytest.mark.slow``).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from oh_my_kb.core import Note, NoteType
from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.services import Indexer, RecentService
from oh_my_kb.storage import DENSE_DIM, IN_MEMORY, QdrantStore

# ---------------------------------------------------------------------------
# Stub embedder helpers
# ---------------------------------------------------------------------------


class _StubEmbedder(Embedder):
    """Deterministic stub: same text → same vector; different text → different."""

    @property
    def dense_dim(self) -> int:
        return DENSE_DIM

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        results: list[EmbeddingResult] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            dense = [digest[i % 32] / 255.0 for i in range(DENSE_DIM)]
            sparse = SparseVector(
                indices=[int.from_bytes(digest[0:2], "little")],
                values=[1.0],
            )
            results.append(EmbeddingResult(dense=dense, sparse=sparse))
        return results


class _CountingEmbedder(_StubEmbedder):
    """Tracks how many times embed_text was called."""

    def __init__(self) -> None:
        self.embed_calls: int = 0

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        self.embed_calls += len(texts)
        return super().embed_texts(texts)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> QdrantStore:
    return QdrantStore(IN_MEMORY)


@pytest.fixture
def embedder() -> _StubEmbedder:
    return _StubEmbedder()


@pytest.fixture
def counting_embedder() -> _CountingEmbedder:
    return _CountingEmbedder()


@pytest.fixture
def indexer(store: QdrantStore, embedder: _StubEmbedder, tmp_path: Path) -> Indexer:
    return Indexer(store=store, embedder=embedder, notes_root=tmp_path)


@pytest.fixture
def recent_service(store: QdrantStore, embedder: _StubEmbedder) -> RecentService:
    return RecentService(store=store, embedder=embedder)


# ---------------------------------------------------------------------------
# Note factory
# ---------------------------------------------------------------------------


def _note(
    *,
    title: str,
    summary: str,
    project: str = "default",
    universe: str = "engineering",
    archived: bool = False,
    days_ago: int = 0,
) -> Note:
    created = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC) - timedelta(days=days_ago)
    return Note(
        title=title,
        type=NoteType.DECISION,
        project=project,
        universe=universe,
        created_at=created,
        summary=summary,
        archived=archived,
    )


# ---------------------------------------------------------------------------
# Missing collection → empty list
# ---------------------------------------------------------------------------


def test_missing_collection_returns_empty_list(recent_service: RecentService) -> None:
    assert recent_service.recent("brand-new") == []


# ---------------------------------------------------------------------------
# Ordering: newest first
# ---------------------------------------------------------------------------


def test_results_ordered_newest_first(indexer: Indexer, recent_service: RecentService) -> None:
    indexer.write_note(_note(title="oldest", summary="oldest note", days_ago=10))
    indexer.write_note(_note(title="middle", summary="middle note", days_ago=5))
    indexer.write_note(_note(title="newest", summary="newest note", days_ago=1))

    results = recent_service.recent("engineering")

    assert len(results) == 3
    assert results[0].title == "newest"
    assert results[1].title == "middle"
    assert results[2].title == "oldest"


# ---------------------------------------------------------------------------
# Limit
# ---------------------------------------------------------------------------


def test_limit_respected(indexer: Indexer, recent_service: RecentService) -> None:
    for i in range(8):
        indexer.write_note(_note(title=f"note-{i}", summary=f"summary {i}", days_ago=i))

    results = recent_service.recent("engineering", limit=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# Project filter
# ---------------------------------------------------------------------------


def test_project_filter(indexer: Indexer, recent_service: RecentService) -> None:
    indexer.write_note(_note(title="alpha-1", summary="alpha note 1", project="alpha"))
    indexer.write_note(_note(title="alpha-2", summary="alpha note 2", project="alpha"))
    indexer.write_note(_note(title="beta-1", summary="beta note 1", project="beta"))

    results = recent_service.recent("engineering", project="alpha")
    assert {r.project for r in results} == {"alpha"}
    assert len(results) == 2


# ---------------------------------------------------------------------------
# Archived filter
# ---------------------------------------------------------------------------


def test_archived_excluded_by_default(indexer: Indexer, recent_service: RecentService) -> None:
    indexer.write_note(_note(title="active", summary="active note"))
    indexer.write_note(_note(title="archived", summary="archived note", archived=True))

    results = recent_service.recent("engineering")
    assert all(not r.archived for r in results)
    assert len(results) == 1


def test_include_archived_returns_both(indexer: Indexer, recent_service: RecentService) -> None:
    indexer.write_note(_note(title="active", summary="active note"))
    indexer.write_note(_note(title="archived", summary="archived note", archived=True))

    results = recent_service.recent("engineering", include_archived=True)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# Since filter
# ---------------------------------------------------------------------------


def test_since_excludes_older_notes(indexer: Indexer, recent_service: RecentService) -> None:
    indexer.write_note(_note(title="recent", summary="recent note", days_ago=3))
    indexer.write_note(_note(title="old", summary="old note", days_ago=14))

    since = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC) - timedelta(days=7)
    results = recent_service.recent("engineering", since=since)

    assert len(results) == 1
    assert results[0].title == "recent"


def test_since_includes_notes_exactly_at_boundary(
    indexer: Indexer, recent_service: RecentService
) -> None:
    """Notes created exactly at the since boundary should be included."""
    # 7 days ago exactly.
    since = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC) - timedelta(days=7)
    indexer.write_note(
        Note(
            title="boundary",
            type=NoteType.DECISION,
            project="default",
            universe="engineering",
            created_at=since,
            summary="note exactly at the boundary",
        )
    )
    results = recent_service.recent("engineering", since=since)
    assert len(results) == 1


# ---------------------------------------------------------------------------
# No-topic path does not call embed_text
# ---------------------------------------------------------------------------


def test_no_topic_does_not_embed(
    store: QdrantStore, counting_embedder: _CountingEmbedder, tmp_path: Path
) -> None:
    indexer = Indexer(store=store, embedder=counting_embedder, notes_root=tmp_path)
    recent_service = RecentService(store=store, embedder=counting_embedder)

    # Reset after indexing (embed_texts is called during write_note).
    indexer.write_note(_note(title="note", summary="some note"))
    counting_embedder.embed_calls = 0

    recent_service.recent("engineering")

    assert counting_embedder.embed_calls == 0


# ---------------------------------------------------------------------------
# No-topic path → score == 0.0
# ---------------------------------------------------------------------------


def test_score_is_zero_when_no_topic(indexer: Indexer, recent_service: RecentService) -> None:
    indexer.write_note(_note(title="note", summary="some note"))

    results = recent_service.recent("engineering")
    assert len(results) == 1
    assert results[0].score == 0.0


# ---------------------------------------------------------------------------
# With-topic path → results narrowed within window
# ---------------------------------------------------------------------------


def test_topic_narrows_within_window(indexer: Indexer, recent_service: RecentService) -> None:
    """Topic path: query for 'qdrant vector search' within a 7-day window.

    Two notes are in the window; the one whose text hashes closer to the query
    should rank first.  Since we use a deterministic hash embedder, we verify
    that the topic note (same text as query) is #1 and the distractor is #2.
    """
    query = "qdrant vector search"
    indexer.write_note(
        _note(title="target", summary=query, days_ago=2)
    )
    indexer.write_note(
        _note(title="distractor", summary="team offsite logistics and travel booking", days_ago=3)
    )
    # Outside the 7-day window — must not appear.
    indexer.write_note(
        _note(title="outside", summary=query, days_ago=10)
    )

    since = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC) - timedelta(days=7)
    results = recent_service.recent("engineering", topic=query, since=since, limit=3)

    ids = {r.title for r in results}
    assert "outside" not in ids, "note outside the since window must not appear"
    assert "target" in ids, "target note must appear"
    # The target should rank first (hash stub: same text → highest similarity).
    assert results[0].title == "target"


def test_topic_path_score_nonzero(indexer: Indexer, recent_service: RecentService) -> None:
    """When topic is provided, score > 0.0 (RRF fusion)."""
    indexer.write_note(_note(title="note", summary="some searchable note"))

    results = recent_service.recent("engineering", topic="searchable note")
    assert len(results) == 1
    assert results[0].score > 0.0
