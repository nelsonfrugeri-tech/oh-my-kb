"""Fast unit tests for :class:`~oh_my_harness.kb.services.recent.RecentService`.

Uses ``QdrantStore(':memory:')`` and a deterministic stub embedder.  Real bge-m3
integration lives in ``test_recent_integration.py`` (``@pytest.mark.slow``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from _helpers import StubEmbedder

from oh_my_harness.kb.core import Note, NoteType
from oh_my_harness.kb.embedding import EmbeddingResult
from oh_my_harness.kb.services import Indexer, RecentService
from oh_my_harness.kb.storage import IN_MEMORY, QdrantStore

# ---------------------------------------------------------------------------
# Local counting subclass — mirrors _CountingStubEmbedder in test_mcp_server.py
# ---------------------------------------------------------------------------


class _CountingEmbedder(StubEmbedder):
    """Tracks how many times embed_texts was called."""

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
def embedder() -> StubEmbedder:
    return StubEmbedder()


@pytest.fixture
def counting_embedder() -> _CountingEmbedder:
    return _CountingEmbedder()


@pytest.fixture
def indexer(store: QdrantStore, embedder: StubEmbedder, tmp_path: Path) -> Indexer:
    return Indexer(store=store, embedder=embedder, notes_root=tmp_path)


@pytest.fixture
def recent_service(store: QdrantStore, embedder: StubEmbedder) -> RecentService:
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


# ---------------------------------------------------------------------------
# With-topic path: since boundary (MAJOR fix — mirrors no-topic boundary test)
# ---------------------------------------------------------------------------


def test_with_topic_since_includes_notes_exactly_at_boundary(
    indexer: Indexer, recent_service: RecentService
) -> None:
    """Notes created exactly at the since boundary must be included in the with-topic path.

    This mirrors the existing ``test_since_includes_notes_exactly_at_boundary`` test
    but exercises the with-topic code path (RRF fusion + Python-side guard).
    """
    since = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC) - timedelta(days=7)
    indexer.write_note(
        Note(
            title="boundary-topic",
            type=NoteType.DECISION,
            project="default",
            universe="engineering",
            created_at=since,
            summary="note exactly at the boundary",
        )
    )
    results = recent_service.recent("engineering", topic="boundary note", since=since)
    assert len(results) == 1
    assert results[0].title == "boundary-topic"


def test_with_topic_since_boundary_handles_tz_correctly(
    indexer: Indexer, recent_service: RecentService
) -> None:
    """With-topic since guard must normalise non-UTC timezones before comparing.

    Indexes a note whose created_at is expressed in +02:00; confirms it appears
    when since is set to the equivalent UTC time (meaning the note is at the boundary).
    """
    tz_plus2 = timezone(timedelta(hours=2))
    # Note created at 2026-05-30 14:00 +02:00 = 2026-05-30 12:00 UTC.
    created_local = datetime(2026, 5, 30, 14, 0, 0, tzinfo=tz_plus2)

    indexer.write_note(
        Note(
            title="tz-note",
            type=NoteType.DECISION,
            project="default",
            universe="engineering",
            created_at=created_local,
            summary="note with non-UTC timezone created_at",
        )
    )

    # since = 2026-05-30 12:00 UTC → note is exactly at boundary → must appear.
    since_utc = datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC)
    results = recent_service.recent("engineering", topic="non-UTC timezone note", since=since_utc)
    titles = [r.title for r in results]
    assert "tz-note" in titles, (
        "Note at exactly the since boundary (in non-UTC tz) must appear in results"
    )

    # since = 2026-05-30 12:00:01 UTC → note is before since → must NOT appear.
    since_after = datetime(2026, 5, 30, 12, 0, 1, tzinfo=UTC)
    results_excl = recent_service.recent(
        "engineering", topic="non-UTC timezone note", since=since_after
    )
    assert all(r.title != "tz-note" for r in results_excl), (
        "Note before since boundary must be excluded"
    )


# ---------------------------------------------------------------------------
# With-topic path + since: undercount prevention (MAJOR fix)
# ---------------------------------------------------------------------------


def test_with_topic_since_does_not_undercount(
    indexer: Indexer, recent_service: RecentService
) -> None:
    """With-topic + since must return `limit` results when enough notes exist in the window.

    Indexes 20 notes inside the 7-day window and 15 notes outside.
    With the old 4x multiplier and limit=10, only 40 candidates were fetched total —
    if many of those 40 happened to be outside the window, we'd get <10 results.
    With the new 10x multiplier, 100 candidates are fetched, ensuring all 20 in-window
    notes are seen and exactly limit=10 are returned.
    """
    since = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC) - timedelta(days=7)

    for i in range(20):
        indexer.write_note(
            _note(title=f"in-window-{i}", summary=f"recent note number {i}", days_ago=i % 7)
        )
    for i in range(15):
        indexer.write_note(
            _note(title=f"outside-{i}", summary=f"old note number {i}", days_ago=10 + i)
        )

    results = recent_service.recent("engineering", topic="recent note", since=since, limit=10)
    assert len(results) == 10, (
        f"Expected 10 results with enough in-window notes, got {len(results)}"
    )
    # All returned notes must be within the window.
    for r in results:
        assert not (r.created_at < since), (
            f"Note '{r.title}' created at {r.created_at} is before since {since}"
        )


# ---------------------------------------------------------------------------
# limit validation
# ---------------------------------------------------------------------------


def test_limit_zero_raises_value_error(recent_service: RecentService) -> None:
    with pytest.raises(ValueError, match="limit must be in"):
        recent_service.recent("engineering", limit=0)


def test_limit_over_100_raises_value_error(recent_service: RecentService) -> None:
    with pytest.raises(ValueError, match="limit must be in"):
        recent_service.recent("engineering", limit=101)
