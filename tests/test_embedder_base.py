from dataclasses import FrozenInstanceError

import pytest

from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector


class _RecordingEmbedder(Embedder):
    """Test double — records calls without loading any model."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    @property
    def dense_dim(self) -> int:
        return 1024

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        self.calls.append(list(texts))
        return [
            EmbeddingResult(
                dense=[0.0] * self.dense_dim,
                sparse=SparseVector(indices=[], values=[]),
            )
            for _ in texts
        ]


def test_embedder_is_abstract_and_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Embedder()  # type: ignore[abstract]


def test_embed_text_delegates_to_embed_texts() -> None:
    e = _RecordingEmbedder()
    e.embed_text("hello")
    assert e.calls == [["hello"]]


def test_embed_text_returns_single_result() -> None:
    e = _RecordingEmbedder()
    result = e.embed_text("hello")
    assert isinstance(result, EmbeddingResult)
    assert len(result.dense) == 1024
    assert isinstance(result.sparse, SparseVector)


def test_sparse_vector_is_frozen() -> None:
    v = SparseVector(indices=[1, 2], values=[0.5, 0.6])
    with pytest.raises(FrozenInstanceError):
        v.indices = [9]  # type: ignore[misc]


def test_embedding_result_is_frozen() -> None:
    r = EmbeddingResult(dense=[0.0], sparse=SparseVector(indices=[], values=[]))
    with pytest.raises(FrozenInstanceError):
        r.dense = [1.0]  # type: ignore[misc]
