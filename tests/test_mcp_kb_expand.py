"""Tests for the ``kb_expand`` MCP tool handler.

Mirrors the pattern established in ``test_mcp_kb_search.py``: a stub embedder,
an in-memory QdrantStore, a real Indexer to seed data, and a real
NavigationService to prove the handler formats output correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from oh_my_harness.kb.core import Note, NoteType
from oh_my_harness.kb.mcp.tools.kb_expand import _MAX_BODY_CHARS, handle_kb_expand
from oh_my_harness.kb.services import Indexer, NavigationService
from oh_my_harness.kb.storage import QdrantStore

# ``store``, ``embedder``, ``indexer`` fixtures are provided by
# tests/conftest.py.


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


async def test_kb_expand_truncates_oversized_body(
    indexer: Indexer, navigation: NavigationService
) -> None:
    """Body exceeding _MAX_BODY_CHARS is capped with a visible truncation marker."""
    long_body = "A" * (_MAX_BODY_CHARS + 500)
    note = _note(title="Big Note", body=long_body)
    indexer.write_note(note)

    result = await handle_kb_expand(navigation, "work", {"id": str(note.id)})

    assert len(result) == 1
    text = result[0].text

    # Truncation marker must be present
    assert "truncated" in text
    assert "500 chars omitted" in text

    # The body section must be capped — the 501st char must not appear in body
    assert "A" * (_MAX_BODY_CHARS + 1) not in text

    # Markers still present
    assert "--- body ---" in text
    assert "--- end body ---" in text
