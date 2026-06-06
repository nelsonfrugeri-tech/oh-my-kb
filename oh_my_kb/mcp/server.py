"""``o-kb-mcp`` — stdio server exposing kb_write and kb_search.

Dependencies (``QdrantStore``, ``BGEM3Embedder``, ``Indexer``,
:class:`SearchService`) are built **once** when the server boots and reused
for every tool invocation — that's the whole point of running an MCP
server instead of doing one-shot CLIs. Universe is server-bound via
``KB_UNIVERSE``; tool inputs cannot widen it.

The handlers themselves live in :mod:`oh_my_kb.mcp.tools` so they can be
unit-tested without touching the SDK; this module only wires them into the
``Server`` instance and runs the stdio transport.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl

from oh_my_kb.embedding import BGEM3Embedder, Embedder
from oh_my_kb.mcp.config import get_active_notes_root, get_active_universe
from oh_my_kb.mcp.resources import list_scribe_resources, read_scribe_resource
from oh_my_kb.mcp.tools import (
    KB_SEARCH_TOOL,
    KB_WRITE_TOOL,
    handle_kb_search,
    handle_kb_write,
)
from oh_my_kb.services import Indexer, SearchService
from oh_my_kb.storage import QdrantStore, get_qdrant_url

SERVER_NAME = "o-kb-mcp"


@dataclass(frozen=True, slots=True)
class KBServerContext:
    """Snapshot of everything the server needs at request time.

    Immutable so multiple coroutines reading the same context can never see
    a half-built dependency graph.
    """

    universe: str
    qdrant_url: str
    notes_root: Path
    store: QdrantStore
    embedder: Embedder
    indexer: Indexer
    search_service: SearchService


def build_context(
    *,
    universe: str | None = None,
    qdrant_url: str | None = None,
    notes_root: Path | None = None,
    store: QdrantStore | None = None,
    embedder: Embedder | None = None,
) -> KBServerContext:
    """Resolve env → concrete deps. Every parameter is overridable for tests."""
    resolved_universe = universe if universe is not None else get_active_universe()
    resolved_url = qdrant_url if qdrant_url is not None else get_qdrant_url()
    resolved_root = (
        notes_root if notes_root is not None else get_active_notes_root(resolved_universe)
    )
    resolved_store = store if store is not None else QdrantStore(resolved_url)
    resolved_embedder = embedder if embedder is not None else BGEM3Embedder()
    indexer = Indexer(
        store=resolved_store,
        embedder=resolved_embedder,
        notes_root=resolved_root,
    )
    search_service = SearchService(store=resolved_store, embedder=resolved_embedder)
    return KBServerContext(
        universe=resolved_universe,
        qdrant_url=resolved_url,
        notes_root=resolved_root,
        store=resolved_store,
        embedder=resolved_embedder,
        indexer=indexer,
        search_service=search_service,
    )


def build_server(context: KBServerContext) -> Server[Any, Any]:
    """Construct a :class:`Server` with kb_write + kb_search registered."""
    server: Server[Any, Any] = Server(SERVER_NAME)

    # mcp's decorator factories aren't typed — silence the strict-mypy
    # noise; the inner function signatures are still typed below.
    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return [KB_WRITE_TOOL, KB_SEARCH_TOOL]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "kb_write":
            return await handle_kb_write(context.indexer, context.universe, arguments)
        if name == "kb_search":
            return await handle_kb_search(
                context.search_service, context.universe, arguments
            )
        return [TextContent(type="text", text=f"unknown tool: {name}")]

    @server.list_resources()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_resources() -> list[Resource]:
        return list_scribe_resources()

    @server.read_resource()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _read_resource(uri: AnyUrl) -> str:
        return read_scribe_resource(str(uri))

    return server


def _log_startup(context: KBServerContext) -> None:
    print(
        (
            f"{SERVER_NAME} ready\n"
            f"  universe   : {context.universe}\n"
            f"  qdrant_url : {context.qdrant_url}\n"
            f"  notes_root : {context.notes_root}\n"
            f"  tools      : kb_write, kb_search\n"
            f"  model      : bge-m3 (lazy — first call triggers load/download ~2 GB)\n"
            f"  resources  : skill://scribe/SKILL.md, skill://scribe/template.md"
        ),
        file=sys.stderr,
        flush=True,
    )


async def _serve() -> None:
    context = build_context()
    context.notes_root.mkdir(parents=True, exist_ok=True)
    server = build_server(context)
    _log_startup(context)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    """``[project.scripts] o-kb-mcp`` entry point."""

    def _handle_sigterm(signum: int, frame: object) -> None:
        # SIGTERM is the standard shutdown signal in containers and systemd.
        # Without this handler asyncio.run raises SystemExit with no message,
        # making container logs silent on graceful shutdown.
        print(f"{SERVER_NAME} stopped (SIGTERM)", file=sys.stderr)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        print(f"{SERVER_NAME} stopped", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    main()
