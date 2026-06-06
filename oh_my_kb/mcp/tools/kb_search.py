"""``kb_search`` MCP tool — hybrid retrieval via :class:`SearchService`.

The handler is a plain ``async def`` taking the dependency plus the
arguments dict, mirroring :mod:`oh_my_kb.mcp.tools.kb_write`. The active
universe is server-bound, not taken from input — search never crosses
universes.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.types import TextContent, Tool

from oh_my_kb.services import SearchResult, SearchService

KB_SEARCH_TOOL = Tool(
    name="kb_search",
    description=(
        "Hybrid-retrieve notes from the active universe by similarity to a "
        "natural-language query. Use when the question is about content or "
        "theme ('what do we know about X?'). Prefer kb_search when the "
        "universe is large or the answer depends on semantic similarity; "
        "prefer navigation (kb_tree / kb_expand) when the answer depends on "
        "structure or relationships. Returns up to top_k ranked summaries — "
        "to read the full body, the 'path' field in each hit points to the "
        ".md file on disk."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 1,
                "description": "Natural-language query.",
            },
            "project": {
                "type": ["string", "null"],
                "minLength": 1,
                "description": "Optional project filter (non-empty string or null).",
            },
            "top_k": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 5,
                "description": "Maximum number of hits.",
            },
            "include_archived": {
                "type": "boolean",
                "default": False,
                "description": "Include archived notes in results.",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)


async def handle_kb_search(
    search_service: SearchService,
    universe: str,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Execute ``kb_search`` against ``search_service`` (server-bound to ``universe``)."""
    query = arguments["query"]
    project = arguments.get("project")
    top_k = int(arguments.get("top_k", 5))
    include_archived = bool(arguments.get("include_archived", False))

    try:
        # search() calls BGEM3Embedder to generate dense + sparse vectors
        # (CPU/GPU-bound).  Running in a thread pool keeps the asyncio event
        # loop free for concurrent MCP messages and the stdio keep-alive.
        hits = await asyncio.to_thread(
            search_service.search,
            query=query,
            universe=universe,
            project=project,
            top_k=top_k,
            include_archived=include_archived,
        )
    except Exception as exc:  # keep the server alive on infrastructure errors
        return [TextContent(type="text", text=f"kb_search: search error — {exc}")]

    if not hits:
        return [
            TextContent(
                type="text",
                text=(
                    f"kb_search: no notes match '{query}' in universe '{universe}'"
                    f"{' (project=' + project + ')' if project else ''}."
                ),
            )
        ]

    return [TextContent(type="text", text=_format_hits(hits, query, universe))]


def _format_hits(hits: list[SearchResult], query: str, universe: str) -> str:
    header = (
        f"kb_search: {len(hits)} hit(s) for '{query}' in universe '{universe}'\n"
    )
    blocks = []
    for rank, hit in enumerate(hits, start=1):
        blocks.append(
            f"[{rank}] id={hit.id}  score={hit.score:.4f}\n"
            f"    title: {hit.title}\n"
            f"    type/project: {hit.type} / {hit.project}\n"
            f"    created_at: {hit.created_at.isoformat()}\n"
            f"    path: {hit.path}\n"
            f"    summary: {hit.summary}"
        )
    return header + "\n" + "\n\n".join(blocks)
