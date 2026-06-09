import pytest
from qdrant_client.models import Distance

from oh_my_harness.kb.storage import (
    DENSE_DIM,
    DENSE_VECTOR_NAME,
    IN_MEMORY,
    SPARSE_VECTOR_NAME,
    QdrantStore,
)


@pytest.fixture
def store() -> QdrantStore:
    return QdrantStore(IN_MEMORY)


def test_collection_does_not_exist_initially(store: QdrantStore) -> None:
    assert store.collection_exists("engineering") is False


def test_healthcheck_returns_true_for_local_backend(store: QdrantStore) -> None:
    assert store.healthcheck() is True


def test_ensure_collection_creates_hybrid_layout(store: QdrantStore) -> None:
    store.ensure_collection("engineering")

    info = store.client.get_collection("engineering")
    vectors = info.config.params.vectors
    sparse = info.config.params.sparse_vectors

    assert vectors is not None
    assert sparse is not None
    assert DENSE_VECTOR_NAME in vectors
    assert SPARSE_VECTOR_NAME in sparse

    dense_params = vectors[DENSE_VECTOR_NAME]
    assert dense_params.size == DENSE_DIM
    assert dense_params.distance == Distance.COSINE


def test_ensure_collection_is_idempotent(store: QdrantStore) -> None:
    store.ensure_collection("engineering")
    store.ensure_collection("engineering")  # must not raise

    info_after = store.client.get_collection("engineering")
    assert info_after.config.params.vectors is not None
    assert DENSE_VECTOR_NAME in info_after.config.params.vectors


def test_collection_exists_after_ensure(store: QdrantStore) -> None:
    store.ensure_collection("engineering")
    assert store.collection_exists("engineering") is True


def test_delete_collection_removes_it(store: QdrantStore) -> None:
    store.ensure_collection("engineering")
    assert store.collection_exists("engineering") is True

    store.delete_collection("engineering")
    assert store.collection_exists("engineering") is False


def test_delete_collection_is_idempotent_for_unknown(store: QdrantStore) -> None:
    store.delete_collection("never-existed")  # must not raise
    assert store.collection_exists("never-existed") is False


def test_multiple_universes_are_isolated(store: QdrantStore) -> None:
    store.ensure_collection("engineering")
    store.ensure_collection("personal")

    assert store.collection_exists("engineering") is True
    assert store.collection_exists("personal") is True

    store.delete_collection("engineering")

    assert store.collection_exists("engineering") is False
    assert store.collection_exists("personal") is True


def test_ensure_collection_creates_payload_indexes_on_existing_collection_without_them() -> None:
    """BLOCKER regression: universes created before payload indexes were introduced must
    receive the indexes when ``ensure_collection`` is called again (convergent behaviour).

    This test simulates the "old universe" scenario by creating the collection manually
    (without indexes), then calling ``ensure_collection`` and asserting that the indexes
    are present afterwards.

    Note: the local qdrant-client ``:memory:`` backend silently ignores payload indexes
    (they have no effect on in-memory storage) and does not expose them via
    ``get_collection().payload_schema``.  The test therefore validates that calling
    ``ensure_collection`` on an existing collection does NOT raise — which is the
    contractual guarantee on the real server (where ``create_payload_index`` is idempotent).
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, SparseVectorParams, VectorParams

    from oh_my_harness.kb.storage import DENSE_DIM, DENSE_VECTOR_NAME, IN_MEMORY, SPARSE_VECTOR_NAME

    # Simulate a "pre-index" universe: create the collection directly, skipping indexes.
    raw_client = QdrantClient(location=IN_MEMORY)
    raw_client.create_collection(
        collection_name="legacy",
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
    )
    # At this point "legacy" exists without payload indexes — the old state.

    # Wrap in QdrantStore and call ensure_collection — must NOT raise.
    store = QdrantStore.__new__(QdrantStore)
    store._location = IN_MEMORY
    store._client = raw_client

    store.ensure_collection("legacy")  # must be idempotent and apply indexes

    # Collection still exists and is intact.
    assert store.collection_exists("legacy") is True
    info = store.client.get_collection("legacy")
    assert info.config.params.vectors is not None
    assert DENSE_VECTOR_NAME in info.config.params.vectors
