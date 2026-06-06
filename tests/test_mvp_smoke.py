"""MVP end-to-end smoke test.

Uses the real bge-m3 embedder — marks ``@pytest.mark.slow`` so normal CI can
deselect it with ``-m 'not slow'`` while the nightly / release pipeline runs it
with ``-m slow``.

Design decisions
----------------
* QdrantStore(IN_MEMORY) — avoids Docker dependency while exercising the full
  Qdrant query API (hybrid search, RRF fusion, scroll, delete).  The in-memory
  backend is sufficient to prove the stack is wired correctly.
* BGEM3Embedder() real — the test verifies that semantic similarity actually
  works (e.g. "vector database" → Qdrant decision note rises to top), which is
  only meaningful with a real model.  Cache is warm after the first load.
* Single test function — all assertions share the same four indexed notes so
  Qdrant state is not re-created between assertions.  Sub-sections are marked
  with comments.

Run with::

    uv run pytest tests/test_mvp_smoke.py -v -m slow
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from oh_my_kb.core import NoteType
from oh_my_kb.core.note import Note
from oh_my_kb.embedding import BGEM3Embedder
from oh_my_kb.services import Indexer, NavigationService, SearchService, reindex_universe
from oh_my_kb.storage import IN_MEMORY, QdrantStore

# ---------------------------------------------------------------------------
# Shared fixtures (session-scoped so bge-m3 loads once per pytest session)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def real_embedder() -> BGEM3Embedder:
    """Load the real bge-m3 model once per session (~5s on first call)."""
    return BGEM3Embedder()


@pytest.fixture(scope="module")
def smoke_store() -> QdrantStore:
    return QdrantStore(IN_MEMORY)


SMOKE_UNIVERSE = "smoke_test"


# ---------------------------------------------------------------------------
# The smoke test
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_mvp_full_flow(
    real_embedder: BGEM3Embedder,
    smoke_store: QdrantStore,
    tmp_path: Path,
) -> None:
    """Full MVP flow: write → search → tree → expand → supersede → reindex."""

    # ------------------------------------------------------------------
    # 0. Setup services
    # ------------------------------------------------------------------
    indexer = Indexer(
        store=smoke_store,
        embedder=real_embedder,
        notes_root=tmp_path,
    )
    search_svc = SearchService(store=smoke_store, embedder=real_embedder)
    nav_svc = NavigationService(store=smoke_store, indexer=indexer)

    base_time = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)

    # ------------------------------------------------------------------
    # 1. Write 4 notes
    # ------------------------------------------------------------------
    note_a = Note(
        title="Decisão de usar Qdrant",
        type=NoteType.DECISION,
        project="backend",
        universe=SMOKE_UNIVERSE,
        created_at=base_time,
        summary=(
            "Decidimos usar Qdrant como banco de dados vetorial por suportar"
            " busca híbrida densa e esparsa."
        ),
        body="Avaliamos Weaviate, Milvus e Qdrant. A escolha final foi Qdrant.",
    )
    note_b = Note(
        title="Incidente no pipeline de deploy",
        type=NoteType.EVENT,
        project="backend",
        universe=SMOKE_UNIVERSE,
        created_at=base_time + timedelta(hours=1),
        summary="Falha no pipeline de CI/CD causou deploy quebrado em produção.",
        body="Root cause: variável de ambiente ausente no stage de build.",
    )
    note_c = Note(
        title="Procedimento de rollback",
        type=NoteType.PROCEDURE,
        project="backend",
        universe=SMOKE_UNIVERSE,
        created_at=base_time + timedelta(hours=2),
        links_out=[note_a.id],
        summary="Passos para realizar rollback seguro da aplicação backend.",
        body="1. Identificar tag estável anterior. 2. Re-deploy.",
    )
    note_d = Note(
        title="Referência sobre React 19",
        type=NoteType.REFERENCE,
        project="frontend",
        universe=SMOKE_UNIVERSE,
        created_at=base_time + timedelta(hours=3),
        summary="Documentação e notas sobre React 19 e as novas concurrent features.",
        body="React 19 traz melhorias de performance e a Actions API.",
    )

    path_a = indexer.write_note(note_a)
    path_b = indexer.write_note(note_b)
    path_c = indexer.write_note(note_c)
    path_d = indexer.write_note(note_d)

    assert path_a.exists()
    assert path_b.exists()
    assert path_c.exists()
    assert path_d.exists()

    # ------------------------------------------------------------------
    # 2. kb_search: "vector database" → note_a on top
    # ------------------------------------------------------------------
    results = search_svc.search(
        query="vector database",
        universe=SMOKE_UNIVERSE,
        include_archived=False,
    )
    assert results, "search returned empty"
    assert results[0].id == str(note_a.id), (
        f"Expected note_a (Qdrant decision) on top, got: {results[0].title}"
    )

    # ------------------------------------------------------------------
    # 3. kb_tree: no project filter → 4 notes, 2 projects
    # ------------------------------------------------------------------
    tree = nav_svc.get_tree(universe=SMOKE_UNIVERSE)
    all_ids = {node.id for nodes in tree.values() for node in nodes}
    assert str(note_a.id) in all_ids
    assert str(note_b.id) in all_ids
    assert str(note_c.id) in all_ids
    assert str(note_d.id) in all_ids
    assert len(tree) == 2, f"Expected 2 projects, got {list(tree.keys())}"
    assert "backend" in tree
    assert "frontend" in tree
    assert len(tree["backend"]) == 3
    assert len(tree["frontend"]) == 1

    # ------------------------------------------------------------------
    # 4. kb_tree: project="backend" → 3 notes
    # ------------------------------------------------------------------
    tree_backend = nav_svc.get_tree(universe=SMOKE_UNIVERSE, project="backend")
    assert "backend" in tree_backend
    assert len(tree_backend["backend"]) == 3
    assert "frontend" not in tree_backend

    # ------------------------------------------------------------------
    # 5. kb_expand: note_c → body + link to note_a resolved
    # ------------------------------------------------------------------
    expanded = nav_svc.expand(note_id=note_c.id, universe=SMOKE_UNIVERSE)
    assert expanded.note.id == note_c.id
    assert len(expanded.links) == 1
    assert expanded.links[0].id == str(note_a.id)

    # ------------------------------------------------------------------
    # 6. Supersede: note_e supersedes note_a
    # ------------------------------------------------------------------
    note_e = Note(
        title="Decisão de usar Qdrant v2",
        type=NoteType.DECISION,
        project="backend",
        universe=SMOKE_UNIVERSE,
        created_at=base_time + timedelta(hours=4),
        supersedes=note_a.id,
        summary=(
            "Revisão da decisão de usar Qdrant: confirmado como vector database"
            " principal com suporte a multi-vector."
        ),
        body="Revisão após 3 meses de uso. Mantemos Qdrant.",
    )
    indexer.write_note(note_e)

    # Mark note_a as archived by updating via write_note.
    archived_a = note_a.model_copy(update={"archived": True})
    indexer.write_note(archived_a)

    # Search WITHOUT archived → note_e on top, note_a absent.
    results_no_arch = search_svc.search(
        query="vector database",
        universe=SMOKE_UNIVERSE,
        include_archived=False,
    )
    result_ids_no_arch = [r.id for r in results_no_arch]
    assert str(note_e.id) in result_ids_no_arch, "note_e should appear in non-archived search"
    assert str(note_a.id) not in result_ids_no_arch, "archived note_a must not appear"

    # Search WITH archived → both appear.
    results_with_arch = search_svc.search(
        query="vector database",
        universe=SMOKE_UNIVERSE,
        include_archived=True,
    )
    result_ids_with_arch = [r.id for r in results_with_arch]
    assert str(note_e.id) in result_ids_with_arch
    assert str(note_a.id) in result_ids_with_arch

    # ------------------------------------------------------------------
    # 7. Move file: move note_d's .md to a sub-directory, run reindex,
    #    confirm payload path updated and read_note_by_id still works.
    # ------------------------------------------------------------------
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    moved_path_d = archive_dir / path_d.name

    # Copy then delete (simulating a manual move outside the MCP tool).
    shutil.copy2(path_d, moved_path_d)
    path_d.unlink()

    assert not path_d.exists()
    assert moved_path_d.exists()

    report = reindex_universe(
        indexer=indexer,
        universe=SMOKE_UNIVERSE,
        notes_root=tmp_path,
    )
    # 5 files scanned: note_b, note_c, note_d (moved), note_e + archived_a written by write_note.
    # note_a's original file may have been overwritten by archived_a — still 5 total on disk.
    assert report.scanned >= 5
    assert report.upserted >= 5
    assert report.removed == 0  # no orphans — moved file still exists

    # Confirm the Qdrant payload now points to the moved path.
    from oh_my_kb.services.indexer import collection_name_for

    collection = collection_name_for(SMOKE_UNIVERSE)
    records = smoke_store.client.retrieve(
        collection_name=collection,
        ids=[str(note_d.id)],
        with_payload=True,
        with_vectors=False,
    )
    assert records, "note_d point missing after reindex"
    stored_rel = records[0].payload["path"]  # type: ignore[index]
    assert stored_rel == str(moved_path_d.relative_to(tmp_path)), (
        f"Expected payload path to point to moved file; got {stored_rel!r}"
    )

    # read_note_by_id must still succeed using the new path.
    recovered = indexer.read_note_by_id(note_d.id, SMOKE_UNIVERSE)
    assert recovered.id == note_d.id
    assert recovered.title == note_d.title

    print(f"\n[smoke] {report}")
    print("[smoke] All assertions passed.")
