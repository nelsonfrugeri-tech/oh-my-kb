"""Semantic-relevance integration test for SearchService with real bge-m3.

Marked ``slow`` because it loads the bge-m3 model. The fast unit tests in
``test_search.py`` cover plumbing (filters, top_k, empty collections); this
one is the only place we assert that *real* semantic similarity moves the
right note to the top of the hybrid-fused ranking.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from oh_my_harness.kb.core import Note, NoteType
from oh_my_harness.kb.embedding import BGEM3Embedder
from oh_my_harness.kb.services import Indexer, SearchService
from oh_my_harness.kb.storage import IN_MEMORY, QdrantStore

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def embedder() -> BGEM3Embedder:
    return BGEM3Embedder()


def test_semantically_close_query_ranks_target_note_first(
    embedder: BGEM3Embedder, tmp_path: Path
) -> None:
    store = QdrantStore(IN_MEMORY)
    indexer = Indexer(store=store, embedder=embedder, notes_root=tmp_path)
    search = SearchService(store=store, embedder=embedder)

    target_summary = (
        "Decisão de usar Qdrant como banco de vetores com busca híbrida"
        " (dense bge-m3 + sparse) e fusão RRF."
    )
    other_summaries = [
        "Procedimento de deploy do serviço web em staging via GitHub Actions.",
        "Evento de incidente no provider de e-mail no dia 12 de maio.",
        "Referência sobre quais frameworks de UI a equipe avalia para 2026.",
    ]

    for idx, summary in enumerate([target_summary, *other_summaries]):
        indexer.write_note(
            Note(
                title=f"nota {idx}",
                type=NoteType.DECISION,
                project="oh-my-harness",
                kb_name="engineering",
                created_at=datetime(2026, 5, 31, 14, 30, tzinfo=UTC),
                summary=summary,
            )
        )

    results = search.search(
        "como armazenamos vetores e fazemos busca híbrida?",
        kb_name="engineering",
        top_k=5,
    )

    assert len(results) >= 1
    assert results[0].summary == target_summary
