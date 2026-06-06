"""Integration test for :class:`RecentService` with the real bge-m3 model.

Marked ``slow`` because it loads the bge-m3 model (~2 GB, cached after first
run).  The fast unit tests in ``test_recent.py`` cover plumbing; this test
proves that the *real* embedder ranks a semantically-close note first within
a time window.

Scenario (from the ai-engineer brief):
- A: "Qdrant vector database architecture" — 6d ago (within 7-day window)
- B: "team offsite logistics and travel booking" — 5d ago (within window)
- C: "Qdrant query API performance benchmarks" — 3d ago (within window)
- D: "Qdrant vector database architecture" — 10d ago (OUTSIDE window)

Query: topic="qdrant vector search", since="7d", limit=3.
Assert: results[0] is A or C, and D is not in results.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from oh_my_kb.core import Note, NoteType
from oh_my_kb.embedding import BGEM3Embedder
from oh_my_kb.services import Indexer, RecentService
from oh_my_kb.storage import IN_MEMORY, QdrantStore

pytestmark = pytest.mark.slow

NOW = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def embedder() -> BGEM3Embedder:
    return BGEM3Embedder()


def _make_note(title: str, summary: str, days_ago: int) -> Note:
    return Note(
        title=title,
        type=NoteType.DECISION,
        project="oh-my-kb",
        universe="engineering",
        created_at=NOW - timedelta(days=days_ago),
        summary=summary,
    )


def test_topic_within_window_ranks_and_excludes(
    embedder: BGEM3Embedder, tmp_path: Path
) -> None:
    store = QdrantStore(IN_MEMORY)
    indexer = Indexer(store=store, embedder=embedder, notes_root=tmp_path)
    recent = RecentService(store=store, embedder=embedder)

    note_a = _make_note(
        "Qdrant vector database architecture",
        "Qdrant vector database architecture — dense and sparse hybrid indexing.",
        days_ago=6,
    )
    note_b = _make_note(
        "Team offsite logistics",
        "team offsite logistics and travel booking for the annual company retreat.",
        days_ago=5,
    )
    note_c = _make_note(
        "Qdrant query API performance benchmarks",
        "Qdrant query API performance benchmarks — latency and throughput analysis.",
        days_ago=3,
    )
    note_d = _make_note(
        "Qdrant vector database architecture (old)",
        "Qdrant vector database architecture — dense and sparse hybrid indexing.",
        days_ago=10,  # OUTSIDE 7-day window
    )

    for note in (note_a, note_b, note_c, note_d):
        indexer.write_note(note)

    since = NOW - timedelta(days=7)
    results = recent.recent(
        "engineering",
        topic="qdrant vector search",
        since=since,
        limit=3,
    )

    result_ids = {str(r.id) for r in results}

    # D is outside the window — must not appear.
    assert str(note_d.id) not in result_ids, (
        f"note_d (10 days ago) must be excluded by the since filter; got ids={result_ids}"
    )

    # Top result should be A or C (both Qdrant-related).
    assert len(results) >= 1
    top_id = str(results[0].id)
    assert top_id in {str(note_a.id), str(note_c.id)}, (
        f"expected top result to be note_a or note_c; got id={top_id} "
        f"(title={results[0].title!r})"
    )
