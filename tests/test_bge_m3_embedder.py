"""Real bge-m3 tests — load the model and exercise it end-to-end.

Marked ``slow`` so CI / fast loops can skip with ``-m 'not slow'``. The DoD
for the embedder issue requires at least one real run, which is what these
provide. The first invocation downloads ~2 GB from HuggingFace; subsequent
runs hit the local HF cache (``~/.cache/huggingface``).
"""

from __future__ import annotations

import pytest

from oh_my_harness.kb.embedding import BGEM3Embedder
from oh_my_harness.kb.storage import DENSE_DIM

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def embedder() -> BGEM3Embedder:
    return BGEM3Embedder()


def test_dense_dim_matches_storage(embedder: BGEM3Embedder) -> None:
    assert embedder.dense_dim == DENSE_DIM == 1024


def test_embed_text_produces_correctly_shaped_result(embedder: BGEM3Embedder) -> None:
    result = embedder.embed_text("Desenho das tools do oh-my-harness.")

    assert len(result.dense) == 1024
    assert all(isinstance(x, float) for x in result.dense[:5])
    assert len(result.sparse.indices) == len(result.sparse.values)
    assert len(result.sparse.indices) > 0
    assert all(isinstance(i, int) for i in result.sparse.indices)
    assert all(isinstance(v, float) for v in result.sparse.values)


def test_embed_texts_preserves_order_and_count(embedder: BGEM3Embedder) -> None:
    texts = [
        "decisão arquitetural sobre as tools",
        "evento de incidente no Qdrant",
        "procedimento de upsert no índice",
    ]
    results = embedder.embed_texts(texts)

    assert len(results) == len(texts)
    # Different inputs must produce different dense vectors (rules out a
    # silent collapse to a single embedding for the whole batch).
    assert results[0].dense != results[1].dense
    assert results[1].dense != results[2].dense


def test_embedding_is_deterministic(embedder: BGEM3Embedder) -> None:
    text = "determinismo importa para os testes"
    a = embedder.embed_text(text)
    b = embedder.embed_text(text)

    assert a.dense == b.dense
    assert a.sparse.indices == b.sparse.indices
    assert a.sparse.values == b.sparse.values


def test_model_is_loaded_once_and_reused(embedder: BGEM3Embedder) -> None:
    embedder.embed_text("primeiro")
    first_ref = embedder._model
    embedder.embed_text("segundo")
    second_ref = embedder._model

    assert first_ref is not None
    assert first_ref is second_ref
