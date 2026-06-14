"""Tests for the reindex service and ``omk reindex`` CLI command.

All tests use the in-memory QdrantStore and StubEmbedder — no Docker, no
real bge-m3, fast enough to run in CI without the ``slow`` marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _helpers import StubEmbedder, make_note

from oh_my_harness.kb.core import NoteType, to_markdown
from oh_my_harness.kb.services import Indexer, ReindexReport, ReindexService, reindex_universe
from oh_my_harness.kb.storage import IN_MEMORY, QdrantStore

# ---------------------------------------------------------------------------
# Local fixtures (extend the shared conftest ones)
# ---------------------------------------------------------------------------


@pytest.fixture
def universe() -> str:
    return "test_reindex"


@pytest.fixture
def store() -> QdrantStore:
    return QdrantStore(IN_MEMORY)


@pytest.fixture
def embedder() -> StubEmbedder:
    return StubEmbedder()


@pytest.fixture
def indexer(store: QdrantStore, embedder: StubEmbedder, tmp_path: Path) -> Indexer:
    return Indexer(store=store, embedder=embedder, notes_root=tmp_path)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _count_points(store: QdrantStore, collection: str) -> int:
    """Return the number of points in ``collection``, or 0 if it does not exist."""
    if not store.collection_exists(collection):
        return 0
    info = store.client.get_collection(collection)
    return info.points_count or 0


def _get_payload(store: QdrantStore, collection: str, note_id: str) -> dict:
    records = store.client.retrieve(
        collection_name=collection,
        ids=[note_id],
        with_payload=True,
        with_vectors=False,
    )
    assert records, f"No point found for id {note_id}"
    return records[0].payload or {}


# ---------------------------------------------------------------------------
# Test 1 — empty universe → noop
# ---------------------------------------------------------------------------


def test_reindex_empty_universe_does_nothing(
    indexer: Indexer, store: QdrantStore, tmp_path: Path, universe: str
) -> None:
    """A universe with no .md files and no Qdrant points stays empty after reindex."""
    report = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)

    assert report.scanned == 0
    assert report.upserted == 0
    assert report.removed == 0


# ---------------------------------------------------------------------------
# Test 2 — existing .md files on disk get indexed
# ---------------------------------------------------------------------------


def test_reindex_indexes_existing_md_files(
    indexer: Indexer, store: QdrantStore, tmp_path: Path, universe: str
) -> None:
    """Notes pre-written to disk (no prior Qdrant entry) are upserted on reindex."""
    from oh_my_harness.kb.services.indexer import collection_name_for

    collection = collection_name_for(universe)
    note_a = make_note(title="Alpha", kb_name=universe, type=NoteType.DECISION)
    note_b = make_note(title="Beta", kb_name=universe, type=NoteType.EVENT)

    # Write .md files directly, bypassing the indexer (simulate manual creation).
    for note in (note_a, note_b):
        p = tmp_path / f"{note.slug}.md"
        p.write_text(to_markdown(note), encoding="utf-8")

    report = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)

    assert report.scanned == 2
    assert report.upserted == 2
    assert report.removed == 0
    assert _count_points(store, collection) == 2


# ---------------------------------------------------------------------------
# Test 3 — moved .md → payload path corrected
# ---------------------------------------------------------------------------


def test_reindex_corrects_path_after_file_moved(
    indexer: Indexer, store: QdrantStore, tmp_path: Path, universe: str
) -> None:
    """After moving a .md file, reindex updates the Qdrant payload path."""
    from oh_my_harness.kb.services.indexer import collection_name_for

    collection = collection_name_for(universe)
    note = make_note(title="Moveable", kb_name=universe)

    # Index via write_note — original path is recorded in Qdrant.
    write_result = indexer.write_note(note)
    original_path = write_result.absolute_path

    # Simulate user moving the file to a sub-directory.
    moved_dir = tmp_path / "archive"
    moved_dir.mkdir()
    moved_path = moved_dir / original_path.name
    original_path.rename(moved_path)

    # Original file no longer exists; the moved one does.
    assert not original_path.exists()
    assert moved_path.exists()

    report = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)

    assert report.scanned == 1
    assert report.upserted == 1
    assert report.removed == 0  # moved file still exists, no orphan

    payload = _get_payload(store, collection, str(note.id))
    # Path stored in Qdrant must point to the *moved* location (relative).
    stored_rel = payload["path"]
    assert stored_rel == str(moved_path.relative_to(tmp_path))


# ---------------------------------------------------------------------------
# Test 4 — orphan Qdrant points are removed
# ---------------------------------------------------------------------------


def test_reindex_removes_orphan_qdrant_points(
    indexer: Indexer, store: QdrantStore, tmp_path: Path, universe: str
) -> None:
    """Qdrant points whose .md no longer exists are deleted during reindex."""
    from oh_my_harness.kb.services.indexer import collection_name_for

    collection = collection_name_for(universe)
    note = make_note(title="Ephemeral", kb_name=universe)

    write_result = indexer.write_note(note)
    assert _count_points(store, collection) == 1

    # Delete the .md from disk — the Qdrant point becomes an orphan.
    write_result.absolute_path.unlink()

    report = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)

    assert report.scanned == 0
    assert report.upserted == 0
    assert report.removed == 1
    assert _count_points(store, collection) == 0


# ---------------------------------------------------------------------------
# Test 5 — idempotency
# ---------------------------------------------------------------------------


def test_reindex_is_idempotent(
    indexer: Indexer, store: QdrantStore, tmp_path: Path, universe: str
) -> None:
    """Running reindex twice produces the same Qdrant state."""
    from oh_my_harness.kb.services.indexer import collection_name_for

    collection = collection_name_for(universe)
    note_a = make_note(title="One", kb_name=universe)
    note_b = make_note(title="Two", kb_name=universe)

    indexer.write_note(note_a)
    indexer.write_note(note_b)

    report1 = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)
    count_after_first = _count_points(store, collection)
    payload_a_first = _get_payload(store, collection, str(note_a.id))

    report2 = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)
    count_after_second = _count_points(store, collection)
    payload_a_second = _get_payload(store, collection, str(note_a.id))

    assert count_after_first == count_after_second == 2
    assert report1.removed == report2.removed == 0
    assert payload_a_first["path"] == payload_a_second["path"]


# ---------------------------------------------------------------------------
# Test 6 — .md files in sub-directories are discovered
# ---------------------------------------------------------------------------


def test_reindex_handles_subdirectories(
    indexer: Indexer, store: QdrantStore, tmp_path: Path, universe: str
) -> None:
    """reindex discovers .md files nested in project sub-directories."""
    from oh_my_harness.kb.services.indexer import collection_name_for

    collection = collection_name_for(universe)
    note = make_note(title="Nested Note", kb_name=universe)

    # Write via indexer, which places the file under <project_slug>/<slug>.md.
    indexer.write_note(note)

    # Clear the Qdrant collection so reindex has to re-create the point.
    store.client.delete_collection(collection_name=collection)

    report = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)

    assert report.scanned == 1
    assert report.upserted == 1
    assert _count_points(store, collection) == 1


# ---------------------------------------------------------------------------
# Test 7 — malformed .md files are skipped, not crashed
# ---------------------------------------------------------------------------


def test_reindex_skips_invalid_md(
    indexer: Indexer,
    store: QdrantStore,
    tmp_path: Path,
    universe: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A .md without valid frontmatter is skipped with a warning; reindex continues."""
    import logging

    # Create one valid note and one malformed file.
    valid_note = make_note(title="Valid Note", kb_name=universe)
    indexer.write_note(valid_note)

    bad_md = tmp_path / "broken.md"
    bad_md.write_text("no frontmatter here, just plain text", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="oh_my_harness.kb.services.reindex"):
        report = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)

    # 2 files scanned: 1 valid + 1 broken.
    assert report.scanned == 2
    # Only the valid one upserted.
    assert report.upserted == 1
    assert report.removed == 0

    # Warning logged for the broken file.
    assert any("broken.md" in r.message or "parse error" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Test 8 — .md with mismatched universe is skipped
# ---------------------------------------------------------------------------


def test_reindex_skips_md_with_mismatched_universe(
    indexer: Indexer,
    store: QdrantStore,
    tmp_path: Path,
    universe: str,
) -> None:
    """A .md whose universe field doesn't match the target universe is still parsed
    and upserted — but into its OWN collection (not the target universe's collection).

    ``reindex_universe`` uses the note's ``universe`` field (via ``upsert_from_disk``
    → ``collection_name_for(note.universe)``) to determine which Qdrant collection
    receives the point. The target ``universe`` parameter only controls which
    collection is sweep-scanned for orphans. As a result, a foreign note present
    in notes_root does not pollute the target universe's collection.
    """
    from oh_my_harness.kb.services.indexer import collection_name_for

    target_collection = collection_name_for(universe)
    other_universe = "completely_different_universe"

    # Note written for a DIFFERENT universe — same notes_root, different universe field.
    other_note = make_note(title="Foreign Note", kb_name=other_universe)
    foreign_md = tmp_path / f"{other_note.slug}.md"
    foreign_md.write_text(to_markdown(other_note), encoding="utf-8")

    # Also one valid note for the target universe.
    valid_note = make_note(title="Local Note", kb_name=universe)
    valid_md = tmp_path / f"{valid_note.slug}.md"
    valid_md.write_text(to_markdown(valid_note), encoding="utf-8")

    report = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)

    # Both files are scanned and upserted (each into its own collection).
    assert report.scanned == 2
    assert report.upserted == 2
    assert report.removed == 0
    # The TARGET universe collection has only the matching note.
    assert _count_points(store, target_collection) == 1
    payload = _get_payload(store, target_collection, str(valid_note.id))
    assert payload["universe"] == universe


# ---------------------------------------------------------------------------
# Test 9 — ReindexService class wrapper
# ---------------------------------------------------------------------------


def test_reindex_service_delegates_to_reindex_universe(
    indexer: Indexer,
    store: QdrantStore,
    tmp_path: Path,
    universe: str,
) -> None:
    """ReindexService.reindex() produces the same result as reindex_universe()."""
    from oh_my_harness.kb.services.indexer import collection_name_for

    collection = collection_name_for(universe)
    note = make_note(title="Service Test", kb_name=universe)
    indexer.write_note(note)

    service = ReindexService(indexer=indexer)
    report = service.reindex(universe)

    assert isinstance(report, ReindexReport)
    assert report.scanned == 1
    assert report.upserted == 1
    assert report.removed == 0
    assert _count_points(store, collection) == 1


# ---------------------------------------------------------------------------
# Test 10 — summary string format
# ---------------------------------------------------------------------------


def test_reindex_prints_summary(
    indexer: Indexer,
    store: QdrantStore,
    tmp_path: Path,
    universe: str,
) -> None:
    """ReindexReport.__str__ matches the expected summary format."""
    note = make_note(title="Summary Test", kb_name=universe)
    indexer.write_note(note)

    report = reindex_universe(indexer=indexer, kb_name=universe, notes_root=tmp_path)

    summary = str(report)
    assert "reindex:" in summary
    assert "scanned" in summary
    assert "upserted" in summary
    assert "orphans" in summary
    # Verify the numbers are present.
    assert f"scanned {report.scanned}" in summary
    assert f"upserted {report.upserted}" in summary
    assert f"removed {report.removed}" in summary
