"""Navigation service.

Provides two cheap, complementary views on a knowledge base so the harness can
*navigate* (not just search) the knowledge base:

* :meth:`NavigationService.get_tree` — a project-grouped map of notes built
  **from Qdrant payloads only**. No filesystem reads, no embedding calls;
  this is what keeps the tree cheap at any knowledge base size.
* :meth:`NavigationService.expand` — the full content of a single note
  (reconstructed from disk) plus the one-hop metadata of the notes its
  ``links_out`` points to (resolved from payloads, again without reading
  more files than the target).

Constructor injects :class:`QdrantStore` and :class:`Indexer`. The Indexer
is reused so the file-reading and round-trip logic lives in exactly one
place — ``read_note_by_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from qdrant_client.models import (
    Condition,
    FieldCondition,
    Filter,
    MatchValue,
)

from oh_my_harness.kb.core import Note
from oh_my_harness.kb.services.indexer import Indexer, collection_name_for
from oh_my_harness.kb.storage import QdrantStore

_SCROLL_PAGE_SIZE: Final[int] = 256


@dataclass(frozen=True, slots=True)
class TreeNode:
    """A node in the navigation tree, hydrated entirely from the payload."""

    id: str
    title: str
    type: str
    project: str
    summary: str
    created_at: str
    archived: bool


@dataclass(frozen=True, slots=True)
class ResolvedLink:
    """Cheap, payload-only view of a note that another note links to."""

    id: str
    title: str
    type: str
    summary: str


@dataclass(frozen=True, slots=True)
class ExpandResult:
    """Full note (from disk) plus its one-hop link neighbourhood."""

    note: Note
    links: list[ResolvedLink]


Tree = dict[str, list[TreeNode]]


class NavigationService:
    def __init__(self, store: QdrantStore, indexer: Indexer) -> None:
        self._store = store
        self._indexer = indexer

    def get_tree(
        self,
        kb_name: str,
        project: str | None = None,
        include_archived: bool = False,
    ) -> Tree:
        """Return ``{project: [TreeNode, ...]}`` for the knowledge base.

        Reads only payloads — never opens a single ``.md`` file. Empty when
        the knowledge base has no collection yet.
        """
        collection = collection_name_for(kb_name)
        if not self._store.collection_exists(collection):
            return {}

        scroll_filter = _build_filter(project=project, include_archived=include_archived)
        tree: Tree = {}
        offset: int | str | UUID | None = None
        while True:
            points, next_offset = self._store.client.scroll(
                collection_name=collection,
                scroll_filter=scroll_filter,
                limit=_SCROLL_PAGE_SIZE,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                node = _payload_to_tree_node(point.payload, point.id)
                tree.setdefault(node.project, []).append(node)
            if next_offset is None:
                break
            offset = next_offset
        return tree

    def expand(self, note_id: UUID, kb_name: str) -> ExpandResult:
        """Reconstruct ``note_id`` from disk and resolve its ``links_out``.

        Links that point to a missing or archived note are silently dropped
        from the result — the harness shouldn't try to follow them.
        """
        note = self._indexer.read_note_by_id(note_id, kb_name)
        if not note.links_out:
            return ExpandResult(note=note, links=[])

        collection = collection_name_for(kb_name)
        link_ids = [str(uid) for uid in note.links_out]
        records = self._store.client.retrieve(
            collection_name=collection,
            ids=link_ids,
            with_payload=True,
            with_vectors=False,
        )

        resolved_by_id: dict[str, ResolvedLink] = {}
        for record in records:
            payload = record.payload or {}
            if bool(payload.get("archived", False)):
                continue
            link = _payload_to_resolved_link(payload, record.id)
            resolved_by_id[link.id] = link

        # Preserve the order declared in note.links_out and drop missing.
        ordered_links = [
            resolved_by_id[str(uid)]
            for uid in note.links_out
            if str(uid) in resolved_by_id
        ]
        return ExpandResult(note=note, links=ordered_links)


def _payload_to_tree_node(payload: dict[str, object] | None, fallback_id: object) -> TreeNode:
    p = payload or {}
    return TreeNode(
        id=str(p.get("id", fallback_id)),
        title=str(p.get("title", "")),
        type=str(p.get("type", "")),
        project=str(p.get("project", "")),
        summary=str(p.get("summary", "")),
        created_at=str(p.get("created_at", "")),
        archived=bool(p.get("archived", False)),
    )


def _payload_to_resolved_link(
    payload: dict[str, object] | None, fallback_id: object
) -> ResolvedLink:
    p = payload or {}
    return ResolvedLink(
        id=str(p.get("id", fallback_id)),
        title=str(p.get("title", "")),
        type=str(p.get("type", "")),
        summary=str(p.get("summary", "")),
    )


def _build_filter(*, project: str | None, include_archived: bool) -> Filter | None:
    must: list[Condition] = []
    must_not: list[Condition] = []
    if project is not None:
        must.append(FieldCondition(key="project", match=MatchValue(value=project)))
    if not include_archived:
        must_not.append(FieldCondition(key="archived", match=MatchValue(value=True)))
    if not must and not must_not:
        return None
    return Filter(must=must or None, must_not=must_not or None)
