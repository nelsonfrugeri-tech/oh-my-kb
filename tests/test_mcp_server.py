"""Lifecycle / wiring tests for the o-kb-mcp server.

We don't spin up the stdio transport here — that's integration work. We
prove the wiring at the function level: ``build_context`` resolves env into
concrete deps, ``build_server`` registers exactly the four tools
(kb_write, kb_search, kb_tree, kb_expand), and the same dependencies are
reused across multiple tool calls (i.e. nothing in the call path
re-instantiates the embedder per request).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _helpers import StubEmbedder

from oh_my_harness.kb.mcp.server import KBServerContext, build_context, build_server
from oh_my_harness.kb.storage import IN_MEMORY, QdrantStore


class _CountingStubEmbedder(StubEmbedder):
    """Subclass of StubEmbedder that counts how many instances have been created.

    The embedding behaviour comes from the shared ``StubEmbedder``; this class
    only adds the instance counter needed by the lifecycle test.
    """

    instances: int = 0

    def __init__(self) -> None:
        type(self).instances += 1


@pytest.fixture(autouse=True)
def reset_embedder_counter() -> None:
    _CountingStubEmbedder.instances = 0


def test_build_context_overrides_all_dependencies(tmp_path: Path) -> None:
    store = QdrantStore(IN_MEMORY)
    embedder = _CountingStubEmbedder()
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
    assert ctx.indexer.notes_root == tmp_path
    assert ctx.search_service._store is store
    # navigation_service must be wired to the same store and indexer
    assert ctx.navigation_service is not None


async def test_build_server_registers_all_tools(tmp_path: Path) -> None:
    """``_list_tools`` must return exactly the five core kb tools."""
    from mcp.types import ListToolsRequest, Tool

    ctx = build_context(
        universe="engineering",
        qdrant_url="http://stub:6333",
        notes_root=tmp_path,
        store=QdrantStore(IN_MEMORY),
        embedder=_CountingStubEmbedder(),
    )
    server = build_server(ctx)
    assert server.name == "o-kb-mcp"

    # The MCP Server stores handlers keyed by the request *class*, not a string.
    list_tools_handler = server.request_handlers.get(ListToolsRequest)
    assert list_tools_handler is not None, "tools/list handler not registered"

    request = ListToolsRequest(method="tools/list")
    response = await list_tools_handler(request)
    # The MCP SDK wraps the result in a ServerResult with a `.root` attribute.
    tools: list[Tool] = response.root.tools  # type: ignore[union-attr]

    tool_names = [t.name for t in tools]
    assert tool_names == [
        "kb_write",
        "kb_search",
        "kb_recent",
        "kb_tree",
        "kb_expand",
    ]


async def test_dependencies_are_built_once_and_reused(tmp_path: Path) -> None:
    """Calling the handlers many times must not create new embedders."""
    embedder = _CountingStubEmbedder()
    ctx = build_context(
        universe="engineering",
        qdrant_url="http://stub:6333",
        notes_root=tmp_path,
        store=QdrantStore(IN_MEMORY),
        embedder=embedder,
    )

    # One embedder created during context construction.
    assert _CountingStubEmbedder.instances == 1

    # Drive both handlers a few times.
    from oh_my_harness.kb.mcp.tools.kb_search import handle_kb_search
    from oh_my_harness.kb.mcp.tools.kb_write import handle_kb_write

    for i in range(3):
        await handle_kb_write(
            ctx.indexer,
            ctx.universe,
            {
                "title": f"Decision {i}",
                "type": "decision",
                "project": "oh-my-harness",
                "summary": f"Summary number {i} of the wiring test.",
            },
        )
        await handle_kb_search(
            ctx.search_service,
            ctx.universe,
            {"query": "Summary number", "top_k": 5},
        )

    # Still one — handlers reuse the embedder built at boot.
    assert _CountingStubEmbedder.instances == 1
