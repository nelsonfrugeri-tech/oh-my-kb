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

from oh_my_harness.kb.embedding import Embedder
from oh_my_harness.kb.services._payload import SearchResult, require_payload_fields
from oh_my_harness.kb.services.indexer import collection_name_for
from oh_my_harness.kb.storage import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, QdrantStore

# Qdrant docs recommend fetching 2x-10x top_k per sub-query so the fusion
# sees a deep enough candidate set from each vector space. 4x is a reasonable
# middle ground between recall coverage and wasted compute.
_PREFETCH_MULTIPLIER = 4

# Re-export the old private name for backwards compatibility with any code
# that imports it directly (e.g. recent.py before refactor).
_require_payload_fields = require_payload_fields

__all__ = ["SearchResult", "SearchService", "_require_payload_fields"]


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
            require_payload_fields(point.id, payload, ("id", "path"))
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
