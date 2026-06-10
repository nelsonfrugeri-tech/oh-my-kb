"""Embedding interface.

Embedding is infrastructure, not domain — it lives outside ``core``. The
:class:`Embedder` ABC defines the contract; the indexer and search layers
will depend only on this interface, so swapping the in-process implementation
for a remote embedding service later is a single-file change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

DenseVector = list[float]


@dataclass(frozen=True, slots=True)
class SparseVector:
    """Qdrant-shaped sparse vector — parallel index/value arrays."""

    indices: list[int]
    values: list[float]


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    dense: DenseVector
    sparse: SparseVector


class Embedder(ABC):
    """Abstract interface for generating dense + sparse text embeddings."""

    @property
    @abstractmethod
    def dense_dim(self) -> int:
        """Dimensionality of the dense vector this embedder produces."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of texts, returning one result per input in order."""

    def embed_text(self, text: str) -> EmbeddingResult:
        """Embed a single text. Delegates to :meth:`embed_texts`."""
        return self.embed_texts([text])[0]
