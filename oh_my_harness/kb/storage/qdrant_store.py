"""Qdrant storage adapter.

Infrastructure-only: this module knows about Qdrant. ``core`` does not.
A single Qdrant instance hosts one collection per ``universe``; search never
crosses universes, so isolation is at the collection boundary.

Collections are created in the hybrid-search layout used by the rest of the
project: a named dense vector (``"dense"``, 1024-dim Cosine — matching
bge-m3) alongside a named sparse vector (``"sparse"``).
"""

from __future__ import annotations

from typing import Final

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, SparseVectorParams, VectorParams

DENSE_VECTOR_NAME: Final[str] = "dense"
SPARSE_VECTOR_NAME: Final[str] = "sparse"
DENSE_DIM: Final[int] = 1024  # bge-m3 dense embedding size
IN_MEMORY: Final[str] = ":memory:"


class QdrantStore:
    """Thin wrapper around :class:`QdrantClient`.

    Pass a URL for a real Qdrant instance, or :data:`IN_MEMORY` (``":memory:"``)
    to use the qdrant-client local backend for tests.
    """

    def __init__(self, location: str) -> None:
        self._location = location
        if location == IN_MEMORY:
            self._client = QdrantClient(location=IN_MEMORY)
        else:
            self._client = QdrantClient(url=location)

    @property
    def client(self) -> QdrantClient:
        """Underlying client — exposed for tests/inspection, not for app code."""
        return self._client

    def healthcheck(self) -> bool:
        """Return ``True`` iff Qdrant responds to a basic request."""
        try:
            self._client.get_collections()
        except Exception:
            return False
        return True

    def collection_exists(self, name: str) -> bool:
        return bool(self._client.collection_exists(collection_name=name))

    def ensure_collection(self, name: str) -> None:
        """Create the hybrid collection if it doesn't exist, and always (re)apply
        payload indexes — making the operation convergent for pre-existing collections.

        A ``DATETIME`` payload index is created on ``created_at`` so that
        :meth:`qdrant_client.QdrantClient.scroll` can use ``order_by`` on
        that field without a full-scan error from the server.  The
        ``KEYWORD`` index on ``project`` speeds up project-filter queries.

        **Why indexes are applied unconditionally:**
        Collections created by earlier versions of the server (before this PR)
        do not have these payload indexes.  The first ``kb_recent`` call on such
        a collection would fail with an ``order_by`` error.  Applying the indexes
        outside the ``if not exists`` branch fixes those universes automatically
        on next boot or first use — no manual migration required.
        ``create_payload_index`` is idempotent on the real Qdrant server (it
        returns success even when the index already exists with the same schema).
        """
        if not self.collection_exists(name):
            self._client.create_collection(
                collection_name=name,
                vectors_config={
                    DENSE_VECTOR_NAME: VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
                },
                sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
            )
        # Always (re)apply payload indexes — idempotent on the real Qdrant server.
        # This ensures universes created before this version receive the indexes
        # on next boot/use without any destructive recreate.
        self._client.create_payload_index(
            collection_name=name,
            field_name="created_at",
            field_schema=PayloadSchemaType.DATETIME,
        )
        self._client.create_payload_index(
            collection_name=name,
            field_name="project",
            field_schema=PayloadSchemaType.KEYWORD,
        )

    def delete_collection(self, name: str) -> None:
        """Delete the collection if it exists (idempotent)."""
        if not self.collection_exists(name):
            return
        self._client.delete_collection(collection_name=name)
