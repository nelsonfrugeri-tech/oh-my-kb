"""End-to-end integration test for the Indexer with the real bge-m3 embedder.

Marked ``slow`` because it loads the bge-m3 model from HuggingFace on first
run (~2 GB). The fast unit tests in ``test_indexer.py`` use a stub embedder
and cover all the behavioral assertions; this one exists so the wiring
between :class:`Indexer`, :class:`QdrantStore` and the real
:class:`BGEM3Embedder` is exercised at least once.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from oh_my_kb.core import Note, NoteType
from oh_my_kb.embedding import BGEM3Embedder
from oh_my_kb.services import Indexer
from oh_my_kb.storage import IN_MEMORY, QdrantStore

pytestmark = pytest.mark.slow


def test_write_then_read_round_trip_with_real_embedder(tmp_path: Path) -> None:
    store = QdrantStore(IN_MEMORY)
    embedder = BGEM3Embedder()
    indexer = Indexer(store=store, embedder=embedder, notes_root=tmp_path)

    note = Note(
        title="Integração ponta a ponta",
        type=NoteType.DECISION,
        project="oh-my-kb",
        universe="engineering",
        created_at=datetime(2026, 5, 31, 14, 30, tzinfo=UTC),
        summary="Validar o caminho completo Indexer → bge-m3 → Qdrant in-memory.",
        body="Conteúdo livre que deve fazer round-trip via from_markdown.",
    )

    result = indexer.write_note(note)
    assert result.absolute_path.is_file()

    restored = indexer.read_note_by_id(note.id, note.universe)
    assert restored == note
