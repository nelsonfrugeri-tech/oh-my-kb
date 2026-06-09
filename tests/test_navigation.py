from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from oh_my_harness.kb.core import Note, NoteType
from oh_my_harness.kb.services import (
    Indexer,
    NavigationService,
    NoteNotFoundError,
    TreeNode,
)
from oh_my_harness.kb.storage import QdrantStore

# ``store``, ``embedder``, ``indexer`` fixtures are provided by
# tests/conftest.py.


@pytest.fixture
def navigation(store: QdrantStore, indexer: Indexer) -> NavigationService:
    return NavigationService(store=store, indexer=indexer)


def _note(
    *,
    title: str = "alguma nota",
    project: str = "oh-my-harness",
    universe: str = "engineering",
    archived: bool = False,
    summary: str | None = None,
    links_out: list[UUID] | None = None,
    note_id: UUID | None = None,
) -> Note:
    payload: dict[str, object] = {
        "title": title,
        "type": NoteType.DECISION,
        "project": project,
        "universe": universe,
        "created_at": datetime(2026, 5, 31, 14, 30, tzinfo=UTC),
        "summary": summary or f"summary of {title}",
        "archived": archived,
    }
    if links_out is not None:
        payload["links_out"] = links_out
    if note_id is not None:
        payload["id"] = note_id
    return Note(**payload)  # type: ignore[arg-type]


# --- get_tree ----------------------------------------------------------


def test_get_tree_missing_collection_returns_empty(navigation: NavigationService) -> None:
    assert navigation.get_tree("brand-new") == {}


def test_get_tree_groups_by_project(
    navigation: NavigationService, indexer: Indexer
) -> None:
    indexer.write_note(_note(title="a1", project="alpha"))
    indexer.write_note(_note(title="a2", project="alpha"))
    indexer.write_note(_note(title="b1", project="beta"))

    tree = navigation.get_tree("engineering")

    assert set(tree.keys()) == {"alpha", "beta"}
    assert len(tree["alpha"]) == 2
    assert len(tree["beta"]) == 1
    assert all(isinstance(node, TreeNode) for nodes in tree.values() for node in nodes)


def test_get_tree_nodes_carry_payload_fields(
    navigation: NavigationService, indexer: Indexer
) -> None:
    note = _note(title="decisão importante", summary="resumo da decisão")
    indexer.write_note(note)

    tree = navigation.get_tree("engineering")
    [node] = tree[note.project]

    assert node.id == str(note.id)
    assert node.title == note.title
    assert node.type == note.type.value
    assert node.project == note.project
    assert node.summary == note.summary
    assert node.created_at == note.created_at.isoformat()
    assert node.archived is False


def test_get_tree_excludes_archived_by_default(
    navigation: NavigationService, indexer: Indexer
) -> None:
    indexer.write_note(_note(title="ativa"))
    indexer.write_note(_note(title="arquivada", archived=True))

    tree = navigation.get_tree("engineering")
    [project] = tree.values()
    titles = {n.title for n in project}
    assert titles == {"ativa"}


def test_get_tree_include_archived_returns_both(
    navigation: NavigationService, indexer: Indexer
) -> None:
    indexer.write_note(_note(title="ativa"))
    indexer.write_note(_note(title="arquivada", archived=True))

    tree = navigation.get_tree("engineering", include_archived=True)
    [project] = tree.values()
    titles = {n.title for n in project}
    assert titles == {"ativa", "arquivada"}


def test_get_tree_filters_by_project(
    navigation: NavigationService, indexer: Indexer
) -> None:
    indexer.write_note(_note(title="a", project="alpha"))
    indexer.write_note(_note(title="b", project="beta"))

    tree = navigation.get_tree("engineering", project="alpha")

    assert set(tree.keys()) == {"alpha"}
    assert len(tree["alpha"]) == 1


def test_get_tree_does_not_read_md_files(
    navigation: NavigationService, indexer: Indexer, tmp_path: Path
) -> None:
    """The navigation tree must be hydrated from payloads only.

    Proof: index a few notes, **delete every .md file on disk**, then build
    the tree. If the implementation read files, this would fail. It works
    because all the data we need is already in the Qdrant payload.
    """
    indexer.write_note(_note(title="a"))
    indexer.write_note(_note(title="b", project="beta"))

    md_files = list(tmp_path.rglob("*.md"))
    assert md_files, "sanity check: indexer should have written files"
    for md in md_files:
        md.unlink()
    assert list(tmp_path.rglob("*.md")) == []

    tree = navigation.get_tree("engineering")

    assert len(tree) == 2
    titles = {n.title for nodes in tree.values() for n in nodes}
    assert titles == {"a", "b"}


# --- expand ------------------------------------------------------------


def test_expand_returns_note_and_resolved_links(
    navigation: NavigationService, indexer: Indexer
) -> None:
    target_a = _note(title="target a", note_id=uuid4())
    target_b = _note(title="target b", note_id=uuid4())
    source = _note(title="source", links_out=[target_a.id, target_b.id])

    indexer.write_note(target_a)
    indexer.write_note(target_b)
    indexer.write_note(source)

    result = navigation.expand(source.id, source.universe)

    assert result.note == source
    assert [link.id for link in result.links] == [str(target_a.id), str(target_b.id)]
    assert result.links[0].title == "target a"
    assert result.links[0].summary == target_a.summary
    assert result.links[1].title == "target b"


def test_expand_without_links_returns_empty_links(
    navigation: NavigationService, indexer: Indexer
) -> None:
    note = _note(title="solo")
    indexer.write_note(note)

    result = navigation.expand(note.id, note.universe)

    assert result.note == note
    assert result.links == []


def test_expand_handles_broken_link_gracefully(
    navigation: NavigationService, indexer: Indexer
) -> None:
    missing = uuid4()
    survivor = _note(title="survivor", note_id=uuid4())
    source = _note(title="source", links_out=[missing, survivor.id])

    indexer.write_note(survivor)
    indexer.write_note(source)

    result = navigation.expand(source.id, source.universe)

    # Broken link silently dropped; surviving target still resolved.
    assert [link.id for link in result.links] == [str(survivor.id)]


def test_expand_skips_archived_links(
    navigation: NavigationService, indexer: Indexer
) -> None:
    archived = _note(title="archived target", archived=True, note_id=uuid4())
    live = _note(title="live target", note_id=uuid4())
    source = _note(title="source", links_out=[archived.id, live.id])

    indexer.write_note(archived)
    indexer.write_note(live)
    indexer.write_note(source)

    result = navigation.expand(source.id, source.universe)

    assert [link.id for link in result.links] == [str(live.id)]


def test_expand_unknown_id_raises(navigation: NavigationService, indexer: Indexer) -> None:
    # Need the collection to exist for the read; index any note first.
    indexer.write_note(_note(title="anchor"))

    with pytest.raises(NoteNotFoundError):
        navigation.expand(UUID(int=0), "engineering")
