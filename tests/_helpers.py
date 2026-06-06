"""Shared test helpers — imported by conftest.py (fixtures) and test modules directly.

This module is *not* a conftest so test files can import from it by name.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from oh_my_kb.core import Note, NoteType
from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.storage import DENSE_DIM

# ---------------------------------------------------------------------------
# Shared stub embedder
# ---------------------------------------------------------------------------


class StubEmbedder(Embedder):
    """Deterministic, fast stand-in for the real bge-m3 model.

    Same text → same vector across calls (so tests can rely on it);
    different text → different vector (so we can tell them apart in
    similarity-based assertions).  No model loading involved.

    Dense: 1 024-dim float vector derived from sha256(text).
    Sparse: 2-entry vector with fixed values [0.5, 0.3].
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


# ---------------------------------------------------------------------------
# Note builder
# ---------------------------------------------------------------------------


def make_note(**overrides: object) -> Note:
    """Build a :class:`~oh_my_kb.core.Note` with project-wide defaults.

    The defaults are chosen so that every test file can call ``make_note()``
    without specifying any arguments and still get a fully valid note that
    passes all model-level validators.

    Supported override keys mirror the ``Note`` constructor.  Use
    ``note_id=<UUID>`` to set the ``id`` field, and
    ``links_out=[uuid4()]`` to add an outbound link.
    """
    payload: dict[str, object] = {
        "title": "Arquitetura do KB",
        "type": NoteType.DECISION,
        "project": "oh-my-kb",
        "universe": "engineering",
        "created_at": datetime(2026, 5, 31, 14, 30, tzinfo=UTC),
        "summary": "Decisão sobre como as camadas se conversam.",
        "body": "# Detalhes\n\nDescrição longa que não vai pro payload.",
        "entities": [],
        "links_out": [],
    }
    # Allow ``note_id`` as an alias for ``id`` (matches the pattern used in
    # test_navigation.py and test_mcp_kb_expand.py).
    if "note_id" in overrides:
        overrides["id"] = overrides.pop("note_id")
    payload.update(overrides)
    return Note(**payload)  # type: ignore[arg-type]
