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

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class WriteResult:
    id: UUID
    slug: str
    relative_path: Path
    absolute_path: Path


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

    @property
    def notes_root(self) -> Path:
        """The universe-scoped directory where this indexer writes notes."""
        return self._notes_root

    def path_for(self, note: Note) -> Path:
        """Return the filesystem path where this note's .md will live.

        ``notes_root`` is already universe-scoped, so only the project
        slug is added under it before the file name.
        """
        return self._notes_root / slugify(note.project) / f"{note.slug}.md"

    def write_note(self, note: Note) -> WriteResult:
        """Persist the note as a .md file and upsert its index entry in Qdrant.

        Idempotent: re-running with the **same** ``note.id`` *and* the same
        ``title``/``created_at`` (i.e. the same slug) updates the existing
        Qdrant point and rewrites the file in place — no duplicate points,
        no duplicate files.

        Scope note: mutating ``title`` or ``created_at`` on an already-indexed
        note changes the slug, which means a new ``.md`` is written at a new
        path while the previous file is left on disk.  Cleaning up stale files
        from slug mutations is out of scope for ``write_note``; it is the
        responsibility of the future ``kb_write`` / update workflow.
        """
        # Operation order is INTENTIONAL and must be preserved:
        # (1) ensure_collection — prerequisite for upsert
        # (2) embed_text         — expensive; fails fast before any mutation
        # (3) upsert             — Qdrant point persisted; idempotent on retry
        # (4) write_text         — .md materialised last; disk never leads index
        #
        # A write_text failure here leaves an orphan Qdrant point (path in
        # payload points to a file that does not exist yet).  That is acceptable
        # because write_note is idempotent — re-running with the same note.id
        # overwrites the point and creates the file.  Reversing steps 3 and 4
        # re-introduces the orphan-.md bug fixed in issue #25.
        collection = collection_name_for(note.universe)
        self._store.ensure_collection(collection)

        path = self.path_for(note)
        relative_path = path.relative_to(self._notes_root)

        embedding = self._embedder.embed_text(note.summary)
        payload = self._payload(note, relative_path)
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

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_markdown(note), encoding="utf-8")
        return WriteResult(
            id=note.id,
            slug=note.slug,
            relative_path=relative_path,
            absolute_path=path,
        )

    def read_note_by_id(self, note_id: UUID, universe: str) -> Note:
        """Load a note's full content from disk using the Qdrant payload's path.

        Raises :class:`NoteNotFoundError` when:
        * no point exists for ``note_id`` in ``universe``'s collection,
        * the payload is missing the ``path`` field,
        * the payload's ``universe`` field does not match the requested
          universe (defence-in-depth against index corruption),
        * the file at the stored path no longer exists on disk.
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
        if payload.get("universe") != universe:
            raise NoteNotFoundError(
                f"note {note_id} payload universe '{payload.get('universe')}' "
                f"does not match requested universe '{universe}'"
            )
        path_str = payload.get("path")
        if not isinstance(path_str, str):
            raise NoteNotFoundError(
                f"note {note_id} payload is missing the 'path' field"
            )
        abs_path = self._notes_root / path_str
        try:
            content = abs_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise NoteNotFoundError(
                f"note {note_id} file not found on disk: {abs_path}"
            ) from exc
        return from_markdown(content)

    def _payload(self, note: Note, relative_path: Path) -> dict[str, Any]:
        return {
            "id": str(note.id),
            "slug": note.slug,
            "title": note.title,
            "type": note.type.value,
            "project": note.project,
            "universe": note.universe,
            "created_at": note.created_at.isoformat(),
            "entities": list(note.entities),
            # Store a path relative to notes_root so the index is portable
            # across machines and notes_root relocations.  Reconstructed in
            # read_note_by_id as ``self._notes_root / path_str``.
            "path": str(relative_path),
            "supersedes": str(note.supersedes) if note.supersedes is not None else None,
            "archived": note.archived,
            "summary": note.summary,
        }
