"""bge-m3 embedder backed by ``FlagEmbedding.BGEM3FlagModel``.

bge-m3 emits dense (1024-dim) and lexical-sparse vectors from a single model
in one forward pass. The sparse output is a per-token-ID weight dict that we
adapt to Qdrant's parallel ``indices``/``values`` shape.

The model is loaded lazily on the first ``embed_*`` call and reused across
calls. Construction is therefore cheap — useful in tests and CLI startup —
and only one process-wide model instance exists per embedder.
"""

from __future__ import annotations

from typing import Final

from FlagEmbedding import BGEM3FlagModel

from oh_my_harness.kb.embedding.base import Embedder, EmbeddingResult, SparseVector

_DENSE_DIM: Final[int] = 1024


class BGEM3Embedder(Embedder):
    DEFAULT_MODEL: Final[str] = "BAAI/bge-m3"

    def __init__(self, model_name: str = DEFAULT_MODEL, *, use_fp16: bool = False) -> None:
        self._model_name = model_name
        self._use_fp16 = use_fp16
        self._model: BGEM3FlagModel | None = None

    @property
    def dense_dim(self) -> int:
        return _DENSE_DIM

    def _load(self) -> BGEM3FlagModel:
        if self._model is None:
            self._model = BGEM3FlagModel(
                self._model_name,
                use_fp16=self._use_fp16,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )
        return self._model

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        model = self._load()
        output = model.encode(texts, return_dense=True, return_sparse=True)
        dense_batch = output["dense_vecs"]
        lexical_batch = output["lexical_weights"]
        results: list[EmbeddingResult] = []
        for i in range(len(texts)):
            dense: list[float] = dense_batch[i].tolist()
            lex: dict[str, float] = lexical_batch[i]
            sparse = SparseVector(
                indices=[int(token_id) for token_id in lex],
                values=[float(weight) for weight in lex.values()],
            )
            results.append(EmbeddingResult(dense=dense, sparse=sparse))
        return results
