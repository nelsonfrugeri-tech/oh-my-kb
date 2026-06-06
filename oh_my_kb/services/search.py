"""Hybrid search service.

Converts a natural-language query into dense + sparse vectors via the
injected :class:`Embedder`, asks Qdrant's Query API to fetch top results for
each vector independently, and fuses the two ranked lists with Reciprocal
Rank Fusion. Filters (``project``, ``archived``) are applied as Qdrant
payload conditions so they run server-side rather than after fusion.

A missing universe collection is *not* an error — it just means "no notes
yet in this universe", and the service returns an empty list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from qdrant_client.models import (
    Condition,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    Prefetch,
)
from qdrant_client.models import (
    SparseVector as QdrantSparseVector,
)

from oh_my_kb.embedding import Embedder
from oh_my_kb.services.indexer import collection_name_for
from oh_my_kb.storage import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, QdrantStore

# Qdrant docs recommend fetching 2x-10x top_k per sub-query so the fusion
# sees a deep enough candidate set from each vector space. 4x is a reasonable
# middle ground between recall coverage and wasted compute.
_PREFETCH_MULTIPLIER = 4


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Payload carried back from a hybrid-search hit.

    ``score`` is an RRF rank-fusion score, not a raw cosine similarity — do
    not interpret it as a probability or threshold against a fixed value.

    ``path`` is **relative to the universe's** ``notes_root`` (matches the
    Indexer payload, kept relative for portability across machines). The
    caller resolves it to an absolute path via the notes_root it already
    knows for the universe being searched.

    Fields intentionally omitted for now: ``universe``, ``entities``,
    ``supersedes``. They can be added when a downstream consumer needs them.
    See issue #9 for the full payload spec discussion.
    """

    id: str
    title: str
    summary: str
    type: str
    project: str
    archived: bool
    created_at: datetime
    path: str
    score: float


class SearchService:
    def __init__(self, store: QdrantStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    def search(
        self,
        query: str,
        universe: str,
        project: str | None = None,
        top_k: int = 5,
        include_archived: bool = False,
    ) -> list[SearchResult]:
        collection = collection_name_for(universe)
        if not self._store.collection_exists(collection):
            return []

        embedding = self._embedder.embed_text(query)
        prefetch_limit = top_k * _PREFETCH_MULTIPLIER
        payload_filter = _build_filter(project=project, include_archived=include_archived)

        # Filters are applied at the prefetch level so each candidate set
        # is already narrowed before RRF fusion runs.
        prefetch = [
            Prefetch(
                query=embedding.dense,
                using=DENSE_VECTOR_NAME,
                filter=payload_filter,
                limit=prefetch_limit,
            ),
            Prefetch(
                query=QdrantSparseVector(
                    indices=embedding.sparse.indices,
                    values=embedding.sparse.values,
                ),
                using=SPARSE_VECTOR_NAME,
                filter=payload_filter,
                limit=prefetch_limit,
            ),
        ]

        response = self._store.client.query_points(
            collection_name=collection,
            prefetch=prefetch,
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )

        results: list[SearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            _require_payload_fields(point.id, payload, ("id", "path"))
            results.append(
                SearchResult(
                    id=str(payload["id"]),
                    title=str(payload.get("title", "")),
                    summary=str(payload.get("summary", "")),
                    type=str(payload.get("type", "")),
                    project=str(payload.get("project", "")),
                    archived=bool(payload.get("archived", False)),
                    created_at=datetime.fromisoformat(str(payload.get("created_at", ""))),
                    path=str(payload["path"]),
                    score=float(point.score),
                )
            )
        return results


def _require_payload_fields(
    point_id: object, payload: dict[str, object], fields: tuple[str, ...]
) -> None:
    """Raise if any required payload field is absent.

    A missing ``id`` or ``path`` means the index is corrupt (written by an
    older version of the Indexer or an external tool that skipped required
    fields). Silently substituting a fallback would hide the corruption and
    produce hard-to-debug downstream errors.
    """
    missing = [f for f in fields if f not in payload]
    if missing:
        raise RuntimeError(
            f"Index point {point_id!r} is missing required payload fields: {missing}. "
            "Re-index the affected notes to repair the index."
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
