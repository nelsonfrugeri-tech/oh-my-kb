from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from oh_my_kb.core import Note, NoteType, from_markdown
from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.services import (
    COLLECTION_PREFIX,
    Indexer,
    NoteNotFoundError,
    WriteResult,
    collection_name_for,
)
from oh_my_kb.storage import (
    DENSE_DIM,
    DENSE_VECTOR_NAME,
    IN_MEMORY,
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


class _StubEmbedder(Embedder):
    """Deterministic, fast stand-in for the real bge-m3 model.

    Same text → same vector across calls (so tests can rely on it),
    different text → different vector (so we can tell them apart in
    e.g. similarity-based assertions later). No model loading involved.
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


@pytest.fixture
def store() -> QdrantStore:
    return QdrantStore(IN_MEMORY)


@pytest.fixture
def embedder() -> _StubEmbedder:
    return _StubEmbedder()


@pytest.fixture
def indexer(store: QdrantStore, embedder: _StubEmbedder, tmp_path: Path) -> Indexer:
    return Indexer(store=store, embedder=embedder, notes_root=tmp_path)


def _make_note(**overrides: object) -> Note:
    payload: dict[str, object] = {
        "title": "Arquitetura do KB",
        "type": NoteType.DECISION,
        "project": "oh-my-kb",
        "universe": "engineering",
        "created_at": datetime(2026, 5, 31, 14, 30, tzinfo=UTC),
        "summary": "Decisão sobre como as camadas se conversam.",
        "body": "# Detalhes\n\nDescrição longa que não vai pro payload.",
        "entities": ["nelson", "qdrant"],
        "links_out": [uuid4()],
    }
    payload.update(overrides)
    return Note(**payload)  # type: ignore[arg-type]


# --- file layout ---------------------------------------------------------


def test_write_note_writes_file_at_expected_path(
    indexer: Indexer, tmp_path: Path
) -> None:
    note = _make_note()
    result = indexer.write_note(note)

    # notes_root is universe-rooted: the CLI/MCP resolves
    # <data_root>/<slug(universe)>/ before constructing the Indexer, so the
    # path under the root is just <slug(project)>/<slug>.md.
    expected = tmp_path / "oh-my-kb" / f"{note.slug}.md"
    assert result.absolute_path == expected
    assert result.absolute_path.is_file()
    assert result.id == note.id
    assert result.slug == note.slug
    assert result.relative_path == Path("oh-my-kb") / f"{note.slug}.md"


def test_write_note_returns_write_result_with_all_fields(
    indexer: Indexer, tmp_path: Path
) -> None:
    note = _make_note()
    result = indexer.write_note(note)

    assert isinstance(result, WriteResult)
    assert result.id == note.id
    assert result.slug == note.slug
    assert result.absolute_path == tmp_path / "oh-my-kb" / f"{note.slug}.md"
    assert result.relative_path == Path("oh-my-kb") / f"{note.slug}.md"
    assert result.absolute_path == indexer.notes_root / result.relative_path


def test_written_file_roundtrips_via_from_markdown(indexer: Indexer) -> None:
    note = _make_note()
    result = indexer.write_note(note)

    restored = from_markdown(result.absolute_path.read_text(encoding="utf-8"))
    assert restored == note


def test_path_slugifies_project(
    indexer: Indexer, tmp_path: Path
) -> None:
    note = _make_note(project="Decisões — Importantes")
    result = indexer.write_note(note)

    assert result.absolute_path.parent == tmp_path / "decisoes-importantes"
    assert result.absolute_path.is_file()


# --- Qdrant side ---------------------------------------------------------


def test_write_note_creates_collection_for_universe(
    indexer: Indexer, store: QdrantStore
) -> None:
    note = _make_note(universe="research")
    collection = collection_name_for("research")
    assert collection == f"{COLLECTION_PREFIX}research"
    assert store.collection_exists(collection) is False

    indexer.write_note(note)
    assert store.collection_exists(collection) is True


def test_payload_has_all_required_fields_and_excludes_body_links_out(
    indexer: Indexer, store: QdrantStore, tmp_path: Path
) -> None:
    note = _make_note()
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
    note = _make_note(supersedes=superseded)
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
    note = _make_note()
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


# --- idempotency ---------------------------------------------------------


def test_write_note_is_idempotent(indexer: Indexer, store: QdrantStore) -> None:
    note = _make_note()
    result_first = indexer.write_note(note)
    result_second = indexer.write_note(note)

    assert result_first == result_second
    assert result_first.absolute_path.is_file()

    collection = collection_name_for(note.universe)
    count_result = store.client.count(collection_name=collection)
    assert count_result.count == 1

    universe_dir = result_first.absolute_path.parent
    md_files = list(universe_dir.glob("*.md"))
    assert len(md_files) == 1


# --- read_note_by_id ----------------------------------------------------


def test_read_note_by_id_round_trips(indexer: Indexer) -> None:
    note = _make_note()
    indexer.write_note(note)

    restored = indexer.read_note_by_id(note.id, note.universe)
    assert restored == note


def test_read_note_by_id_raises_when_missing(indexer: Indexer) -> None:
    # Need a collection to retrieve from first — create one but with a
    # different id than what we query.
    note = _make_note()
    indexer.write_note(note)

    with pytest.raises(NoteNotFoundError):
        indexer.read_note_by_id(UUID(int=0), note.universe)


def test_read_note_by_id_raises_when_file_deleted(
    indexer: Indexer, tmp_path: Path
) -> None:
    """FileNotFoundError from the FS must surface as NoteNotFoundError."""
    note = _make_note()
    result = indexer.write_note(note)
    result.absolute_path.unlink()  # simulate the file being removed from disk

    with pytest.raises(NoteNotFoundError):
        indexer.read_note_by_id(note.id, note.universe)


def test_read_note_by_id_raises_on_universe_mismatch(
    indexer: Indexer, store: QdrantStore
) -> None:
    """Payload universe mismatch triggers NoteNotFoundError (defence-in-depth)."""
    note = _make_note(universe="engineering")
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
    note = _make_note()

    with pytest.raises(RuntimeError, match="embedder failed"):
        broken.write_note(note)

    assert not broken.path_for(note).exists()


def test_write_note_leaves_no_file_on_upsert_failure(
    store: QdrantStore, embedder: _StubEmbedder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    indexer = Indexer(store=store, embedder=embedder, notes_root=tmp_path)
    note = _make_note()

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
    store: QdrantStore, embedder: _StubEmbedder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """write_md fails after embed+upsert OK: Qdrant point stays (retry is idempotent)."""
    indexer = Indexer(store=store, embedder=embedder, notes_root=tmp_path)
    note = _make_note()

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
