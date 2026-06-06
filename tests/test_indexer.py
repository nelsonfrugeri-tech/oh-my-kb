from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _helpers import StubEmbedder, make_note

from oh_my_kb.core import from_markdown
from oh_my_kb.embedding import Embedder, EmbeddingResult
from oh_my_kb.services import (
    COLLECTION_PREFIX,
    Indexer,
    NoteNotFoundError,
    collection_name_for,
)
from oh_my_kb.storage import (
    DENSE_DIM,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    QdrantStore,
)


class _BrokenEmbedder(Embedder):
    """Always raises — simulates OOM / model failure."""

    @property
    def dense_dim(self) -> int:
        return DENSE_DIM

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        raise RuntimeError("embedder failed")


# --- file layout ---------------------------------------------------------


def test_write_note_writes_file_at_expected_path(
    indexer: Indexer, tmp_path: Path
) -> None:
    note = make_note()
    path = indexer.write_note(note)

    # notes_root is universe-rooted: the CLI/MCP resolves
    # <data_root>/<slug(universe)>/ before constructing the Indexer, so the
    # path under the root is just <slug(project)>/<slug>.md.
    expected = tmp_path / "oh-my-kb" / f"{note.slug}.md"
    assert path == expected
    assert path.is_file()


def test_written_file_roundtrips_via_from_markdown(indexer: Indexer) -> None:
    note = make_note()
    path = indexer.write_note(note)

    restored = from_markdown(path.read_text(encoding="utf-8"))
    assert restored == note


def test_path_slugifies_project(
    indexer: Indexer, tmp_path: Path
) -> None:
    note = make_note(project="Decisões — Importantes")
    path = indexer.write_note(note)

    assert path.parent == tmp_path / "decisoes-importantes"
    assert path.is_file()


# --- Qdrant side ---------------------------------------------------------


def test_write_note_creates_collection_for_universe(
    indexer: Indexer, store: QdrantStore
) -> None:
    note = make_note(universe="research")
    collection = collection_name_for("research")
    assert collection == f"{COLLECTION_PREFIX}research"
    assert store.collection_exists(collection) is False

    indexer.write_note(note)
    assert store.collection_exists(collection) is True


def test_payload_has_all_required_fields_and_excludes_body_links_out(
    indexer: Indexer, store: QdrantStore, tmp_path: Path
) -> None:
    note = make_note()
    indexer.write_note(note)

    collection = collection_name_for(note.universe)
    records = store.client.retrieve(
        collection_name=collection,
        ids=[str(note.id)],
        with_payload=True,
        with_vectors=False,
    )
    assert len(records) == 1
    payload = records[0].payload
    assert payload is not None

    assert set(payload.keys()) == {
        "id",
        "slug",
        "title",
        "type",
        "project",
        "universe",
        "created_at",
        "entities",
        "path",
        "supersedes",
        "archived",
        "summary",
    }
    assert payload["id"] == str(note.id)
    assert payload["slug"] == note.slug
    assert payload["title"] == note.title
    assert payload["type"] == note.type.value
    assert payload["project"] == note.project
    assert payload["universe"] == note.universe
    assert payload["created_at"] == note.created_at.isoformat()
    assert payload["entities"] == list(note.entities)
    # path is stored relative to notes_root; reconstruct to verify the file exists
    assert (tmp_path / payload["path"]).is_file()
    assert payload["supersedes"] is None
    assert payload["archived"] is False
    assert payload["summary"] == note.summary

    assert "body" not in payload
    assert "links_out" not in payload


def test_payload_supersedes_serialized_as_uuid_string(indexer: Indexer, store: QdrantStore) -> None:
    superseded = uuid4()
    note = make_note(supersedes=superseded)
    indexer.write_note(note)

    collection = collection_name_for(note.universe)
    records = store.client.retrieve(
        collection_name=collection,
        ids=[str(note.id)],
        with_payload=True,
    )
    assert records[0].payload is not None
    assert records[0].payload["supersedes"] == str(superseded)


def test_point_has_dense_and_sparse_named_vectors(
    indexer: Indexer, store: QdrantStore
) -> None:
    note = make_note()
    indexer.write_note(note)

    collection = collection_name_for(note.universe)
    records = store.client.retrieve(
        collection_name=collection,
        ids=[str(note.id)],
        with_payload=False,
        with_vectors=True,
    )
    vectors = records[0].vector
    assert isinstance(vectors, dict)
    assert DENSE_VECTOR_NAME in vectors
    assert SPARSE_VECTOR_NAME in vectors
    assert len(vectors[DENSE_VECTOR_NAME]) == DENSE_DIM
    # Regression guard: stub must produce at least 2 sparse entries so that
    # dot-product ranking is non-trivial (prevents regression to 1 sparse entry).
    sparse = vectors[SPARSE_VECTOR_NAME]
    assert len(sparse.indices) >= 2, (
        "sparse vector must have at least 2 entries to preserve ranking utility"
    )


# --- idempotency ---------------------------------------------------------


def test_write_note_is_idempotent(indexer: Indexer, store: QdrantStore) -> None:
    note = make_note()
    path_first = indexer.write_note(note)
    path_second = indexer.write_note(note)

    assert path_first == path_second
    assert path_first.is_file()

    collection = collection_name_for(note.universe)
    count_result = store.client.count(collection_name=collection)
    assert count_result.count == 1

    universe_dir = path_first.parent
    md_files = list(universe_dir.glob("*.md"))
    assert len(md_files) == 1


# --- read_note_by_id ----------------------------------------------------


def test_read_note_by_id_round_trips(indexer: Indexer) -> None:
    note = make_note()
    indexer.write_note(note)

    restored = indexer.read_note_by_id(note.id, note.universe)
    assert restored == note


def test_read_note_by_id_raises_when_missing(indexer: Indexer) -> None:
    # Need a collection to retrieve from first — create one but with a
    # different id than what we query.
    note = make_note()
    indexer.write_note(note)

    with pytest.raises(NoteNotFoundError):
        indexer.read_note_by_id(UUID(int=0), note.universe)


def test_read_note_by_id_raises_when_file_deleted(
    indexer: Indexer, tmp_path: Path
) -> None:
    """FileNotFoundError from the FS must surface as NoteNotFoundError."""
    note = make_note()
    path = indexer.write_note(note)
    path.unlink()  # simulate the file being removed from disk

    with pytest.raises(NoteNotFoundError):
        indexer.read_note_by_id(note.id, note.universe)


def test_read_note_by_id_raises_on_universe_mismatch(
    indexer: Indexer, store: QdrantStore
) -> None:
    """Payload universe mismatch triggers NoteNotFoundError (defence-in-depth)."""
    note = make_note(universe="engineering")
    indexer.write_note(note)

    # Manually corrupt the payload to simulate a mis-indexed point.
    collection = collection_name_for("engineering")
    records = store.client.retrieve(
        collection_name=collection,
        ids=[str(note.id)],
        with_payload=True,
        with_vectors=False,
    )
    payload = dict(records[0].payload or {})
    payload["universe"] = "wrong-universe"
    from qdrant_client.models import PointStruct

    store.client.upsert(
        collection_name=collection,
        points=[
            PointStruct(
                id=str(note.id),
                vector=records[0].vector or {},
                payload=payload,
            )
        ],
    )

    with pytest.raises(NoteNotFoundError):
        indexer.read_note_by_id(note.id, "engineering")


# --- atomicity: no orphan .md on failure --------------------------------


def test_write_note_leaves_no_file_on_embedder_failure(
    store: QdrantStore, tmp_path: Path
) -> None:
    broken = Indexer(store=store, embedder=_BrokenEmbedder(), notes_root=tmp_path)
    note = make_note()

    with pytest.raises(RuntimeError, match="embedder failed"):
        broken.write_note(note)

    assert not broken.path_for(note).exists()


def test_write_note_leaves_no_file_on_upsert_failure(
    store: QdrantStore, embedder: StubEmbedder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    indexer = Indexer(store=store, embedder=embedder, notes_root=tmp_path)
    note = make_note()

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(store.client, "upsert", _fail)

    with pytest.raises(RuntimeError, match="qdrant down"):
        indexer.write_note(note)

    assert not indexer.path_for(note).exists()

    collection = collection_name_for(note.universe)
    records = store.client.retrieve(
        collection_name=collection,
        ids=[str(note.id)],
        with_payload=False,
        with_vectors=False,
    )
    assert len(records) == 0


def test_write_note_leaves_qdrant_point_on_write_md_failure(
    store: QdrantStore, embedder: StubEmbedder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """write_md fails after embed+upsert OK: Qdrant point stays (retry is idempotent)."""
    indexer = Indexer(store=store, embedder=embedder, notes_root=tmp_path)
    note = make_note()

    def _fail_write(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _fail_write)

    with pytest.raises(OSError, match="disk full"):
        indexer.write_note(note)

    collection = collection_name_for(note.universe)
    records = store.client.retrieve(
        collection_name=collection,
        ids=[str(note.id)],
        with_payload=False,
        with_vectors=False,
    )
    assert len(records) == 1
    assert not indexer.path_for(note).exists()
