"""Indexer — application service that writes a note and indexes it.

Orchestrates the three layers below it:

* ``core`` — the :class:`Note` model and markdown serialization,
* ``storage`` — the :class:`QdrantStore` adapter,
* ``embedding`` — the :class:`Embedder` interface.

Dependencies arrive by constructor injection so tests can use the
``QdrantStore(':memory:')`` backend and a stub embedder. No env var lookups
happen here — the CLI/MCP layer resolves the per-universe ``notes_root``
and passes a concrete ``Path`` to the constructor.

Collection layout: each ``universe`` maps to its own Qdrant collection named
``kb_<slug(universe)>``. Per-note files live under
``<notes_root>/<slug(project)>/<note.slug>.md`` — ``notes_root`` is already
universe-scoped, so the indexer adds only the project subdirectory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final
from uuid import UUID

from qdrant_client.models import PointStruct
from qdrant_client.models import SparseVector as QdrantSparseVector

from oh_my_kb.core import Note, from_markdown, slugify, to_markdown
from oh_my_kb.embedding import Embedder
from oh_my_kb.storage import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, QdrantStore

COLLECTION_PREFIX: Final[str] = "kb_"


class NoteNotFoundError(LookupError):
    """Raised when ``read_note_by_id`` finds no point with the requested id."""


def collection_name_for(universe: str) -> str:
    """Return the Qdrant collection name for a given ``universe``.

    Convention: ``kb_<slug(universe)>``. Search never crosses universes, so
    isolation is at the collection boundary.
    """
    return f"{COLLECTION_PREFIX}{slugify(universe)}"


class Indexer:
    def __init__(self, store: QdrantStore, embedder: Embedder, notes_root: Path) -> None:
        self._store = store
        self._embedder = embedder
        self._notes_root = notes_root

    def path_for(self, note: Note) -> Path:
        """Return the filesystem path where this note's .md will live.

        ``notes_root`` is already universe-scoped, so only the project
        slug is added under it before the file name.
        """
        return self._notes_root / slugify(note.project) / f"{note.slug}.md"

    def write_note(self, note: Note) -> Path:
        """Persist the note as a .md file and upsert its index entry in Qdrant.

        Idempotent: re-running with the same ``note.id`` updates the existing
        Qdrant point and rewrites the file in place — no duplicate points,
        no duplicate files.
        """
        collection = collection_name_for(note.universe)
        self._store.ensure_collection(collection)

        path = self.path_for(note)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_markdown(note), encoding="utf-8")

        embedding = self._embedder.embed_text(note.summary)
        payload = self._payload(note, path)
        point = PointStruct(
            id=str(note.id),
            vector={
                DENSE_VECTOR_NAME: embedding.dense,
                SPARSE_VECTOR_NAME: QdrantSparseVector(
                    indices=embedding.sparse.indices,
                    values=embedding.sparse.values,
                ),
            },
            payload=payload,
        )
        self._store.client.upsert(collection_name=collection, points=[point])
        return path

    def read_note_by_id(self, note_id: UUID, universe: str) -> Note:
        """Load a note's full content from disk using the Qdrant payload's path.

        Raises :class:`NoteNotFoundError` if no point exists for ``note_id``
        in ``universe``'s collection.
        """
        collection = collection_name_for(universe)
        records = self._store.client.retrieve(
            collection_name=collection,
            ids=[str(note_id)],
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            raise NoteNotFoundError(
                f"note {note_id} not found in universe '{universe}'"
            )
        payload = records[0].payload or {}
        path_str = payload.get("path")
        if not isinstance(path_str, str):
            raise NoteNotFoundError(
                f"note {note_id} payload is missing the 'path' field"
            )
        content = Path(path_str).read_text(encoding="utf-8")
        return from_markdown(content)

    @staticmethod
    def _payload(note: Note, path: Path) -> dict[str, Any]:
        return {
            "id": str(note.id),
            "slug": note.slug,
            "title": note.title,
            "type": note.type.value,
            "project": note.project,
            "universe": note.universe,
            "created_at": note.created_at.isoformat(),
            "entities": list(note.entities),
            "path": str(path.resolve()),
            "supersedes": str(note.supersedes) if note.supersedes is not None else None,
            "archived": note.archived,
            "summary": note.summary,
        }
