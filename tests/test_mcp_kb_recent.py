"""Unit tests for the ``kb_recent`` MCP handler.

Uses ``QdrantStore(':memory:')`` and a stub embedder so no real model or
Docker is required.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from _helpers import StubEmbedder

from oh_my_harness.kb.core import Note, NoteType
from oh_my_harness.kb.mcp.tools.kb_recent import handle_kb_recent
from oh_my_harness.kb.services import Indexer, RecentService
from oh_my_harness.kb.storage import IN_MEMORY, QdrantStore

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
def indexer(store: QdrantStore, embedder: StubEmbedder, tmp_path: Path) -> Indexer:
    return Indexer(store=store, embedder=embedder, notes_root=tmp_path)


@pytest.fixture
def recent_service(store: QdrantStore, embedder: StubEmbedder) -> RecentService:
    return RecentService(store=store, embedder=embedder)


# ---------------------------------------------------------------------------
# Note factory
# ---------------------------------------------------------------------------

NOW = datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC)


def _note(
    *,
    title: str,
    summary: str,
    project: str = "default",
    universe: str = "engineering",
    archived: bool = False,
    days_ago: int = 0,
) -> Note:
    return Note(
        title=title,
        type=NoteType.DECISION,
        project=project,
        universe=universe,
        created_at=NOW - timedelta(days=days_ago),
        summary=summary,
        archived=archived,
    )


# ---------------------------------------------------------------------------
# Happy path — no args → recent N
# ---------------------------------------------------------------------------


async def test_happy_path_returns_recent_notes(
    indexer: Indexer, recent_service: RecentService
) -> None:
    indexer.write_note(_note(title="note-1", summary="first note", days_ago=1))
    indexer.write_note(_note(title="note-2", summary="second note", days_ago=2))
    indexer.write_note(_note(title="note-3", summary="third note", days_ago=3))

    result = await handle_kb_recent(recent_service, "engineering", {})

    assert len(result) == 1
    text = result[0].text
    assert "kb_recent:" in text
    assert "3 note(s)" in text
    assert "note-1" in text
    assert "note-2" in text
    assert "note-3" in text


# ---------------------------------------------------------------------------
# created_at is visible in each hit
# ---------------------------------------------------------------------------


async def test_created_at_visible_in_output(
    indexer: Indexer, recent_service: RecentService
) -> None:
    indexer.write_note(_note(title="dated-note", summary="a note with a date", days_ago=3))

    result = await handle_kb_recent(recent_service, "engineering", {})
    text = result[0].text
    assert "created_at:" in text


# ---------------------------------------------------------------------------
# No-topic path: score is labelled "n/a" (not omitted, not a numeric value)
# ---------------------------------------------------------------------------


async def test_no_topic_labels_score_n_a(
    indexer: Indexer, recent_service: RecentService
) -> None:
    """When no topic is provided, score must be labelled 'n/a (ordered by time)'
    so the LLM doesn't interpret a numeric 0.0 as a bad relevance score."""
    indexer.write_note(_note(title="note", summary="some note"))

    result = await handle_kb_recent(recent_service, "engineering", {})
    text = result[0].text
    # "n/a" label must appear; raw numeric score must NOT appear.
    assert "score: n/a" in text
    assert "score: 0.0" not in text


# ---------------------------------------------------------------------------
# With-topic path: score line appears
# ---------------------------------------------------------------------------


async def test_with_topic_shows_score_line(
    indexer: Indexer, recent_service: RecentService
) -> None:
    indexer.write_note(_note(title="note", summary="qdrant vector database"))

    result = await handle_kb_recent(
        recent_service, "engineering", {"topic": "qdrant vector database"}
    )
    text = result[0].text
    assert "score:" in text


# ---------------------------------------------------------------------------
# Since filter
# ---------------------------------------------------------------------------


async def test_since_filter_applied(
    indexer: Indexer, recent_service: RecentService
) -> None:
    indexer.write_note(_note(title="recent", summary="recent note", days_ago=2))
    indexer.write_note(_note(title="old", summary="old note", days_ago=20))

    result = await handle_kb_recent(recent_service, "engineering", {"since": "7d"})
    text = result[0].text
    assert "recent" in text
    assert "old" not in text


# ---------------------------------------------------------------------------
# Project filter
# ---------------------------------------------------------------------------


async def test_project_filter(indexer: Indexer, recent_service: RecentService) -> None:
    indexer.write_note(_note(title="alpha-note", summary="alpha summary", project="alpha"))
    indexer.write_note(_note(title="beta-note", summary="beta summary", project="beta"))

    result = await handle_kb_recent(recent_service, "engineering", {"project": "alpha"})
    text = result[0].text
    assert "alpha-note" in text
    assert "beta-note" not in text


# ---------------------------------------------------------------------------
# include_archived toggle
# ---------------------------------------------------------------------------


async def test_archived_excluded_by_default(
    indexer: Indexer, recent_service: RecentService
) -> None:
    indexer.write_note(_note(title="active", summary="active note"))
    indexer.write_note(_note(title="archived", summary="archived note", archived=True))

    result = await handle_kb_recent(recent_service, "engineering", {})
    text = result[0].text
    assert "active" in text
    assert "archived" not in text


async def test_include_archived_shows_archived(
    indexer: Indexer, recent_service: RecentService
) -> None:
    indexer.write_note(_note(title="active", summary="active note"))
    indexer.write_note(_note(title="arch-note", summary="archived note text", archived=True))

    result = await handle_kb_recent(
        recent_service, "engineering", {"include_archived": True}
    )
    text = result[0].text
    assert "arch-note" in text


# ---------------------------------------------------------------------------
# Invalid since → clear text error, not exception
# ---------------------------------------------------------------------------


async def test_invalid_since_returns_clear_text_not_exception(
    recent_service: RecentService,
) -> None:
    result = await handle_kb_recent(
        recent_service, "engineering", {"since": "last-tuesday"}
    )
    assert len(result) == 1
    text = result[0].text
    assert "kb_recent:" in text
    assert "invalid" in text.lower() or "since" in text.lower()


# ---------------------------------------------------------------------------
# No-hits friendly message
# ---------------------------------------------------------------------------


async def test_no_hits_friendly_message(recent_service: RecentService) -> None:
    result = await handle_kb_recent(recent_service, "brand-new", {})

    assert len(result) == 1
    text = result[0].text
    assert "kb_recent:" in text
    assert "no notes" in text
    assert "brand-new" in text


async def test_no_hits_friendly_message_includes_filters(
    indexer: Indexer, recent_service: RecentService
) -> None:
    # Index something so the collection exists, but filter to a project that has nothing.
    indexer.write_note(_note(title="alpha", summary="alpha note", project="alpha"))

    result = await handle_kb_recent(
        recent_service, "engineering", {"project": "nope", "since": "7d"}
    )
    text = result[0].text
    assert "project=nope" in text
    assert "since=7d" in text
