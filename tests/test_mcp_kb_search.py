from __future__ import annotations

from datetime import UTC, datetime

from oh_my_harness.kb.core import Note, NoteType
from oh_my_harness.kb.mcp.tools.kb_search import handle_kb_search
from oh_my_harness.kb.services import Indexer, SearchService

# ``store``, ``embedder``, ``indexer``, ``search_service`` fixtures are
# provided by tests/conftest.py.


def _note(summary: str, project: str = "oh-my-harness") -> Note:
    return Note(
        title=summary[:40] or "note",
        type=NoteType.DECISION,
        project=project,
        kb_name="engineering",
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
