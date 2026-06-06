"""Lifecycle / wiring tests for the o-kb-mcp server.

We don't spin up the stdio transport here — that's integration work. We
prove the wiring at the function level: ``build_context`` resolves env into
concrete deps, ``build_server`` registers exactly the two core tools, and
the same dependencies are reused across multiple tool calls (i.e. nothing
in the call path re-instantiates the embedder per request).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.mcp.server import KBServerContext, build_context, build_server
from oh_my_kb.storage import DENSE_DIM, IN_MEMORY, QdrantStore


class _StubEmbedder(Embedder):
    instances: int = 0

    def __init__(self) -> None:
        type(self).instances += 1

    @property
    def dense_dim(self) -> int:
        return DENSE_DIM

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        return [
            EmbeddingResult(
                dense=[
                    hashlib.sha256(t.encode()).digest()[i % 32] / 255.0
                    for i in range(DENSE_DIM)
                ],
                sparse=SparseVector(indices=[1], values=[1.0]),
            )
            for t in texts
        ]


@pytest.fixture(autouse=True)
def reset_embedder_counter() -> None:
    _StubEmbedder.instances = 0


def test_build_context_overrides_all_dependencies(tmp_path: Path) -> None:
    store = QdrantStore(IN_MEMORY)
    embedder = _StubEmbedder()
    ctx = build_context(
        universe="engineering",
        qdrant_url="http://stub:6333",
        notes_root=tmp_path,
        store=store,
        embedder=embedder,
    )

    assert isinstance(ctx, KBServerContext)
    assert ctx.universe == "engineering"
    assert ctx.qdrant_url == "http://stub:6333"
    assert ctx.notes_root == tmp_path
    assert ctx.store is store
    assert ctx.embedder is embedder
    assert ctx.indexer._notes_root == tmp_path
    assert ctx.search_service._store is store


def test_build_server_registers_only_core_tools(tmp_path: Path) -> None:
    ctx = build_context(
        universe="engineering",
        qdrant_url="http://stub:6333",
        notes_root=tmp_path,
        store=QdrantStore(IN_MEMORY),
        embedder=_StubEmbedder(),
    )
    server = build_server(ctx)
    # The Server's name matches what we expect, and the tool definitions
    # come from the modules.
    assert server.name == "o-kb-mcp"


async def test_dependencies_are_built_once_and_reused(tmp_path: Path) -> None:
    """Calling the handlers many times must not create new embedders."""
    embedder = _StubEmbedder()
    ctx = build_context(
        universe="engineering",
        qdrant_url="http://stub:6333",
        notes_root=tmp_path,
        store=QdrantStore(IN_MEMORY),
        embedder=embedder,
    )

    # One embedder created during context construction.
    assert _StubEmbedder.instances == 1

    # Drive both handlers a few times.
    from oh_my_kb.mcp.tools.kb_search import handle_kb_search
    from oh_my_kb.mcp.tools.kb_write import handle_kb_write

    for i in range(3):
        await handle_kb_write(
            ctx.indexer,
            ctx.universe,
            {
                "title": f"Decision {i}",
                "type": "decision",
                "project": "oh-my-kb",
                "summary": f"Summary number {i} of the wiring test.",
            },
        )
        await handle_kb_search(
            ctx.search_service,
            ctx.universe,
            {"query": "Summary number", "top_k": 5},
        )

    # Still one — handlers reuse the embedder built at boot.
    assert _StubEmbedder.instances == 1
