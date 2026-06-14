"""Temporal-recall service — list notes ordered by ``created_at`` descending.

:class:`RecentService` is the answer to *time-based* queries: "what changed
recently", "latest decisions on project X", "what happened in the last 7 days".
It differs from :class:`SearchService` (semantic similarity on content) and
:class:`NavigationService` (structural map): ``recent`` orders by ``created_at``
and optionally narrows by ``topic`` within the window.

No-topic path
-------------
Uses ``client.scroll`` with ``OrderBy(key="created_at", direction=Direction.DESC)``
so the database returns results pre-sorted.  No embedder call is made —
``BGEM3Embedder`` is heavy and the no-topic path is the common case.

With-topic path
---------------
Uses the same dense+sparse Prefetch + RRF fusion as :class:`SearchService`.
The ``since`` guard is applied **Python-side** because the qdrant-client 1.17
``Range`` filter only accepts ``float`` for ``gte`` — it does not accept ISO
strings or datetimes.

.. # TODO(qdrant-datetime-range): once Qdrant server ships a proper datetime
   # index type, replace the Python-side ``created_at`` guard with a server-side
   # ``DatetimeRange`` filter inside each Prefetch for better performance.

Return type
-----------
Reuses :class:`~oh_my_harness.kb.services.search.SearchResult` from the search module.
When ``topic`` is absent, ``score`` is set to ``0.0`` — do *not* interpret it as
a relevance score; it only signals "ordered by time, no fusion ranking applied".
"""

from __future__ import annotations

from datetime import datetime

from qdrant_client.models import (
    Condition,
    Direction,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    OrderBy,
    Prefetch,
)
from qdrant_client.models import (
    SparseVector as QdrantSparseVector,
)

from oh_my_harness.kb.embedding import Embedder, EmbeddingResult
from oh_my_harness.kb.services._payload import SearchResult, require_payload_fields
from oh_my_harness.kb.services.indexer import collection_name_for
from oh_my_harness.kb.services.temporal import is_before_since
from oh_my_harness.kb.storage import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, QdrantStore

# 10x multiplier for the with-topic path: the since filter runs Python-side,
# so with a restrictive window, many of the 4x candidates could be outside
# the window and the caller would receive fewer than `limit` results even when
# more qualifying notes exist.  10x provides a deeper candidate pool while
# remaining cheap (RRF over in-memory results, not extra round-trips).
# The no-topic path also uses this multiplier for its over-fetch when `since`
# is set — it is equally cheap because the scroll results are already sorted.
_PREFETCH_MULTIPLIER = 10


_TOPIC_CACHE_MAX = 64


class RecentService:
    """List notes ordered by creation time, with optional topic-based ranking.

    Constructor is intentionally identical to :class:`SearchService` so both
    services share the same ``QdrantStore`` and ``Embedder`` instances that are
    built once at server boot.
    """

    def __init__(self, store: QdrantStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder
        # Simple LRU-style in-memory cache for topic embeddings.
        # bge-m3 takes 50-500ms per call; repeated calls with the same topic
        # (common in a conversation session) get served from cache.
        self._topic_cache: dict[str, EmbeddingResult] = {}

    def _embed_topic(self, topic: str) -> EmbeddingResult:
        """Embed *topic*, returning a cached result when available."""
        if topic in self._topic_cache:
            return self._topic_cache[topic]
        emb: EmbeddingResult = self._embedder.embed_text(topic)
        if len(self._topic_cache) >= _TOPIC_CACHE_MAX:
            # Evict oldest entry (insertion-order guaranteed in Python 3.7+).
            self._topic_cache.pop(next(iter(self._topic_cache)))
        self._topic_cache[topic] = emb
        return emb

    def recent(
        self,
        kb_name: str,
        *,
        project: str | None = None,
        topic: str | None = None,
        since: datetime | None = None,
        limit: int = 10,
        include_archived: bool = False,
    ) -> list[SearchResult]:
        """Return notes in the knowledge base ordered newest-first.

        Parameters
        ----------
        kb_name:
            Active knowledge base; maps to a Qdrant collection via
            ``collection_name_for(kb_name)``.
        project:
            Optional payload filter — only notes whose ``project`` field matches.
        topic:
            Optional natural-language topic.  When supplied the method embeds
            the topic text and uses RRF fusion to rank by relevance within the
            time window.  When absent, results are ordered purely by
            ``created_at`` descending and ``score`` is ``0.0``.
        since:
            Tz-aware UTC datetime.  Notes with ``created_at < since`` are
            excluded (Python-side guard; see module docstring).
        limit:
            Maximum number of results to return (1-50).
        include_archived:
            When ``False`` (default) archived notes are excluded.

        Returns
        -------
        list[SearchResult]
            Ordered newest-first (no-topic) or by RRF score (with-topic).
            Empty list when the collection does not exist.

        Notes
        -----
        ``score`` is ``0.0`` for the no-topic path — the caller (MCP handler)
        should omit or label it "n/a" to avoid misleading the LLM.
        """
        if limit < 1 or limit > 100:
            raise ValueError(f"limit must be in [1, 100], got {limit}")

        collection = collection_name_for(kb_name)
        if not self._store.collection_exists(collection):
            return []

        payload_filter = _build_filter(project=project, include_archived=include_archived)

        if topic is None:
            return self._scroll_recent(
                collection=collection,
                payload_filter=payload_filter,
                since=since,
                limit=limit,
            )

        # With-topic path: embed and use RRF fusion (cached per topic).
        embedding = self._embed_topic(topic)
        prefetch_limit = limit * _PREFETCH_MULTIPLIER

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
            limit=limit * _PREFETCH_MULTIPLIER,  # fetch more, then Python-filter by since
            with_payload=True,
            with_vectors=False,
        )

        results: list[SearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            require_payload_fields(point.id, payload, ("id", "path"))
            created_at = datetime.fromisoformat(str(payload.get("created_at", "")))

            # Python-side since guard — normalise both sides to UTC via helper so
            # the with-topic path is consistent with the no-topic path.
            # TODO(qdrant-datetime-range): replace with server-side filter once
            # Qdrant supports a proper datetime Range for payload conditions.
            if since is not None and is_before_since(created_at, since):
                continue

            results.append(
                SearchResult(
                    id=str(payload["id"]),
                    title=str(payload.get("title", "")),
                    summary=str(payload.get("summary", "")),
                    type=str(payload.get("type", "")),
                    project=str(payload.get("project", "")),
                    archived=bool(payload.get("archived", False)),
                    created_at=created_at,
                    path=str(payload["path"]),
                    score=float(point.score),
                )
            )
            if len(results) >= limit:
                break

        return results

    def _scroll_recent(
        self,
        *,
        collection: str,
        payload_filter: Filter | None,
        since: datetime | None,
        limit: int,
    ) -> list[SearchResult]:
        """No-topic path: scroll ordered by ``created_at`` descending.

        ``score`` is always ``0.0`` — the MCP handler should label it "n/a".
        """
        # Fetch more than limit so the Python-side since filter doesn't leave
        # us short.  With limit ≤ 50 a 4x over-fetch is cheap.
        fetch_limit = limit * _PREFETCH_MULTIPLIER if since is not None else limit

        points, _next_offset = self._store.client.scroll(
            collection_name=collection,
            scroll_filter=payload_filter,
            order_by=OrderBy(key="created_at", direction=Direction.DESC),
            limit=fetch_limit,
            with_payload=True,
            with_vectors=False,
        )

        results: list[SearchResult] = []
        for point in points:
            payload = point.payload or {}
            require_payload_fields(point.id, payload, ("id", "path"))
            created_at = datetime.fromisoformat(str(payload.get("created_at", "")))

            # Python-side since guard — normalise both sides to UTC via helper.
            # TODO(qdrant-datetime-range): replace with server-side filter once
            # Qdrant supports a proper datetime Range for payload conditions.
            if since is not None and is_before_since(created_at, since):
                continue

            results.append(
                SearchResult(
                    id=str(payload["id"]),
                    title=str(payload.get("title", "")),
                    summary=str(payload.get("summary", "")),
                    type=str(payload.get("type", "")),
                    project=str(payload.get("project", "")),
                    archived=bool(payload.get("archived", False)),
                    created_at=created_at,
                    path=str(payload["path"]),
                    score=0.0,
                )
            )
            if len(results) >= limit:
                break

        return results


def _build_filter(*, project: str | None, include_archived: bool) -> Filter | None:
    """Build a Qdrant payload filter for project + archived conditions."""
    must: list[Condition] = []
    must_not: list[Condition] = []
    if project is not None:
        must.append(FieldCondition(key="project", match=MatchValue(value=project)))
    if not include_archived:
        must_not.append(FieldCondition(key="archived", match=MatchValue(value=True)))
    if not must and not must_not:
        return None
    return Filter(must=must or None, must_not=must_not or None)
