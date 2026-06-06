"""Smoke / end-to-end test with the real bge-m3 embedder.

Marked ``@pytest.mark.slow`` — excluded from the normal CI run via
``-m "not slow"``.  Run explicitly with:

    uv run pytest tests/test_smoke_e2e.py -v

This file exercises the full pipeline:
1. Index notes with the real embedder.
2. Search.
3. Navigate (tree + expand with link resolution).
4. Supersede a note (archive + replace).
5. Verify archived notes are excluded from search.
6. Move a .md file on disk and reindex — verify payload path updated.
7. Second reindex run is idempotent (removed == 0).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oh_my_kb.core import Note, NoteType
from oh_my_kb.embedding import BGEM3Embedder
from oh_my_kb.services import (
    Indexer,
    NavigationService,
    SearchService,
    collection_name_for,
    reindex_universe,
)
from oh_my_kb.storage import IN_MEMORY, QdrantStore

# ---------------------------------------------------------------------------
# Module-scoped embedder — loaded once for the whole file.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def embedder() -> BGEM3Embedder:
    """Load bge-m3 once for the entire module."""
    return BGEM3Embedder()


# ---------------------------------------------------------------------------
# The full flow as a single test so the embedder is loaded only once.
# ---------------------------------------------------------------------------

UNIVERSE = "smoke_e2e"


def _note(
    title: str,
    summary: str,
    project: str = "smoke-project",
    universe: str = UNIVERSE,
    note_type: NoteType = NoteType.DECISION,
    links_out: list | None = None,
    supersedes: object = None,
    archived: bool = False,
) -> Note:
    """Build a Note with sensible defaults for the smoke test."""
    kwargs: dict = {
        "title": title,
        "type": note_type,
        "project": project,
        "universe": universe,
        "summary": summary,
        "body": f"# {title}\n\n{summary}",
        "links_out": links_out or [],
        "archived": archived,
    }
    if supersedes is not None:
        kwargs["supersedes"] = supersedes
    return Note(**kwargs)


@pytest.mark.slow
def test_full_flow_with_real_embedder(
    embedder: BGEM3Embedder,
    tmp_path: Path,
) -> None:
    """7-step smoke test: index → search → tree → expand → supersede → reindex x2."""
    store = QdrantStore(IN_MEMORY)
    indexer = Indexer(store=store, embedder=embedder, notes_root=tmp_path)
    search_svc = SearchService(store=store, embedder=embedder)
    nav_svc = NavigationService(store=store, indexer=indexer)
    collection = collection_name_for(UNIVERSE)

    # -----------------------------------------------------------------------
    # Step 1: index 4 notes with the real embedder.
    # -----------------------------------------------------------------------
    note_arch = _note(
        title="Architecture Decision: Event Sourcing for KB Store",
        summary=(
            "We decided to adopt event sourcing as the primary storage mechanism "
            "for the knowledge base because it provides a complete audit trail, "
            "enables temporal queries, and simplifies undo/redo semantics. "
            "This was chosen over a mutable-document store after a trade-off analysis "
            "weighing operational complexity against correctness guarantees."
        ),
        project="architecture",
    )
    note_api = _note(
        title="API Design: RESTful Conventions for KB Endpoints",
        summary=(
            "All knowledge-base HTTP endpoints will follow REST level 2 conventions: "
            "resource-based URLs, standard HTTP verbs, and JSON payloads. "
            "GraphQL was evaluated and rejected for this iteration because the "
            "query surface is simple and the added tooling cost outweighs the benefit. "
            "Versioning will use URL path prefixes (/v1/, /v2/) for explicit contracts."
        ),
        project="api",
    )
    note_infra = _note(
        title="Infrastructure: Qdrant as Vector Store",
        summary=(
            "Qdrant was selected as the vector store because it supports hybrid search "
            "(dense + sparse vectors in one query), has a stable Python client, "
            "can run locally via Docker for development, and scales to cloud for production. "
            "Pinecone was eliminated due to vendor lock-in concerns and monthly cost at scale. "
            "Weaviate was eliminated due to schema complexity overhead for our use case."
        ),
        project="infra",
    )
    note_bgem3 = _note(
        title="Embedding: BGE-M3 Dual-Encoder Model",
        summary=(
            "BGE-M3 was chosen as the embedding model because it produces both dense "
            "and lexical-sparse vectors in a single forward pass, enabling hybrid search "
            "without running two separate models. The model is multilingual, open-weight, "
            "and can be run locally on CPU (no GPU required for inference at our scale). "
            "OpenAI ada-002 was rejected due to API dependency and per-token cost."
        ),
        project="infra",
        links_out=[note_infra.id],
    )

    indexer.write_note(note_arch)
    indexer.write_note(note_api)
    indexer.write_note(note_infra)
    indexer.write_note(note_bgem3)

    # Verify all 4 notes are in Qdrant.
    collection_info = store.client.get_collection(collection)
    assert collection_info.points_count == 4, (
        f"Expected 4 points after indexing, got {collection_info.points_count}"
    )

    # -----------------------------------------------------------------------
    # Step 2: search — the Qdrant + infra query should surface the infra note.
    # -----------------------------------------------------------------------
    results = search_svc.search(
        query="vector store for hybrid semantic search",
        universe=UNIVERSE,
        top_k=3,
    )
    assert results, "Search returned no results"
    top_ids = {r.id for r in results}
    assert str(note_infra.id) in top_ids, (
        f"Expected infra note in top results; got ids={top_ids}"
    )

    # -----------------------------------------------------------------------
    # Step 3: get_tree — should see 3 distinct projects.
    # -----------------------------------------------------------------------
    tree = nav_svc.get_tree(universe=UNIVERSE)
    assert len(tree) == 3, f"Expected 3 projects in tree, got {list(tree.keys())}"
    assert "architecture" in tree
    assert "api" in tree
    assert "infra" in tree
    assert len(tree["infra"]) == 2, "Expected 2 notes under 'infra' project"

    # -----------------------------------------------------------------------
    # Step 4: expand note_bgem3 — its links_out should resolve to note_infra.
    # -----------------------------------------------------------------------
    expand = nav_svc.expand(note_bgem3.id, universe=UNIVERSE)
    assert expand.note.id == note_bgem3.id
    assert len(expand.links) == 1, (
        f"Expected 1 resolved link for note_bgem3, got {len(expand.links)}"
    )
    assert expand.links[0].id == str(note_infra.id)

    # -----------------------------------------------------------------------
    # Step 5: supersede note_infra — archive it and create v2.
    # -----------------------------------------------------------------------
    note_infra_archived = note_infra.model_copy(update={"archived": True})
    indexer.write_note(note_infra_archived)

    note_infra_v2 = _note(
        title="Infrastructure: Qdrant v2 — Managed Cloud Deployment",
        summary=(
            "Following the successful local-Qdrant phase we are migrating to Qdrant Cloud "
            "for the production environment. This removes our operational burden of managing "
            "Docker containers, provides automatic backups, and gives us a dedicated cluster "
            "with SLA guarantees. The collection schema and hybrid-search configuration "
            "remain unchanged — only the connection URL and authentication change."
        ),
        project="infra",
        supersedes=note_infra.id,
    )
    indexer.write_note(note_infra_v2)

    # -----------------------------------------------------------------------
    # Step 6: search after supersede — archived note should not appear.
    # -----------------------------------------------------------------------
    results_v2 = search_svc.search(
        query="vector store for hybrid semantic search",
        universe=UNIVERSE,
        top_k=5,
        include_archived=False,
    )
    result_ids = {r.id for r in results_v2}
    assert str(note_infra.id) not in result_ids, (
        "Archived note_infra should be excluded from search"
    )
    assert str(note_infra_v2.id) in result_ids, (
        "note_infra_v2 should appear in search results"
    )

    # -----------------------------------------------------------------------
    # Step 7a: move note_bgem3's .md to a different sub-directory, rewrite
    #          its content (to reflect the move), then run reindex.
    #          Verify payload["path"] in Qdrant is updated.
    # -----------------------------------------------------------------------
    original_md_path = indexer.path_for(note_bgem3)
    assert original_md_path.exists(), f"Original .md not found: {original_md_path}"

    moved_dir = tmp_path / "archive" / "infra"
    moved_dir.mkdir(parents=True, exist_ok=True)
    moved_md_path = moved_dir / original_md_path.name
    original_md_path.rename(moved_md_path)
    assert moved_md_path.exists()
    assert not original_md_path.exists()

    report1 = reindex_universe(
        indexer=indexer,
        universe=UNIVERSE,
        notes_root=tmp_path,
    )

    # The moved note was upserted.
    assert report1.upserted >= 1, f"Expected at least 1 upserted, got {report1}"

    # Verify payload path updated to moved location.
    records = store.client.retrieve(
        collection_name=collection,
        ids=[str(note_bgem3.id)],
        with_payload=True,
        with_vectors=False,
    )
    assert records, "note_bgem3 not found in Qdrant after reindex"
    stored_path = records[0].payload.get("path") if records[0].payload else None
    expected_rel = str(moved_md_path.relative_to(tmp_path))
    assert stored_path == expected_rel, (
        f"Expected payload path '{expected_rel}', got '{stored_path}'"
    )

    # -----------------------------------------------------------------------
    # Step 7b: second reindex — idempotent, removed == 0.
    # -----------------------------------------------------------------------
    report2 = reindex_universe(
        indexer=indexer,
        universe=UNIVERSE,
        notes_root=tmp_path,
    )
    assert report2.removed == 0, (
        f"Second reindex should remove 0 orphans, got removed={report2.removed}"
    )
