"""``kb_recent`` MCP tool — temporal recall via :class:`RecentService`.

Use for TEMPORAL questions about the active universe — 'latest
decisions/events', 'what changed recently', 'news on project X'.  Differs
from ``kb_search`` (semantic similarity on content) and ``kb_tree``
(structural map): ``kb_recent`` orders by ``created_at`` and optionally
narrows by topic within the window.

Accepted ``since`` formats: ``'7d'`` / ``'24h'`` / ``'90m'`` / ``'2w'`` (relative,
case-insensitive), ISO date ``'2026-06-01'``, or ISO datetime ``'2026-06-01T00:00:00+00:00'``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from mcp.types import TextContent, Tool

from oh_my_harness.kb.services import RecentService, SearchResult
from oh_my_harness.kb.services.temporal import parse_since

KB_RECENT_TOOL = Tool(
    name="kb_recent",
    description=(
        "Use for TEMPORAL questions about the active universe — 'latest "
        "decisions/events', 'what changed recently', 'news on project X'. "
        "Differs from kb_search (semantic similarity on content) and kb_tree "
        "(structural map): kb_recent orders by created_at and optionally "
        "narrows by topic within the window. "
        "Omit 'topic' for pure temporal recall (newest first); add 'topic' to "
        "rank by semantic relevance within the window. "
        "Chain with kb_expand(id=...) to read the full body of any hit. "
        "Accepted 'since' formats: '7d' / '24h' / '90m' / '2w' (relative, "
        "case-insensitive), ISO date '2026-06-01', or ISO datetime "
        "'2026-06-01T00:00:00+00:00'."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project": {
                "type": ["string", "null"],
                "minLength": 1,
                "description": "Optional project filter (non-empty string or null).",
            },
            "topic": {
                "type": ["string", "null"],
                "minLength": 1,
                "description": (
                    "Optional topic to rank results by relevance within the time window. "
                    "When absent, results are ordered by created_at descending."
                ),
            },
            "since": {
                "type": ["string", "null"],
                "minLength": 1,
                "description": (
                    "Optional time window. Accepted: '7d' / '24h' / '90m' (relative), "
                    "ISO date '2026-06-01', or ISO datetime '2026-06-01T00:00:00+00:00'."
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
                "description": "Maximum number of results to return.",
            },
            "include_archived": {
                "type": "boolean",
                "default": False,
                "description": "Include archived notes in results.",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
)


async def handle_kb_recent(
    recent_service: RecentService,
    universe: str,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Execute ``kb_recent`` against ``recent_service`` (server-bound to ``universe``)."""
    project: str | None = arguments.get("project")
    topic: str | None = arguments.get("topic")
    since_raw: str | None = arguments.get("since")
    limit = int(arguments.get("limit", 10))
    include_archived = bool(arguments.get("include_archived", False))

    # Resolve the since string → UTC datetime before hitting the service.
    since: datetime | None = None
    if since_raw is not None:
        try:
            since = parse_since(since_raw, now=datetime.now(tz=UTC))
        except ValueError as exc:
            return [TextContent(type="text", text=f"kb_recent: {exc}")]

    try:
        hits = await asyncio.to_thread(
            recent_service.recent,
            universe,
            project=project,
            topic=topic,
            since=since,
            limit=limit,
            include_archived=include_archived,
        )
    except Exception as exc:  # keep the server alive on infrastructure errors
        return [TextContent(type="text", text=f"kb_recent: error — {exc}")]

    if not hits:
        filter_summary = _filter_summary(project=project, since_raw=since_raw, topic=topic)
        return [
            TextContent(
                type="text",
                text=(
                    f"kb_recent: no notes found in knowledge base '{universe}'"
                    f"{filter_summary}."
                ),
            )
        ]

    return [
        TextContent(
            type="text",
            text=_format_hits(hits, universe, topic=topic, since_raw=since_raw, project=project),
        )
    ]


def _filter_summary(
    *,
    project: str | None,
    since_raw: str | None,
    topic: str | None,
) -> str:
    parts: list[str] = []
    if project:
        parts.append(f"project={project}")
    if since_raw:
        parts.append(f"since={since_raw}")
    if topic:
        parts.append(f"topic={topic!r}")
    return f" ({', '.join(parts)})" if parts else ""


def _format_hits(
    hits: list[SearchResult],
    universe: str,
    *,
    topic: str | None,
    since_raw: str | None = None,
    project: str | None = None,
) -> str:
    # Build filter context for the header so the LLM sees what constraints were active.
    filter_parts: list[str] = []
    if since_raw:
        filter_parts.append(f"since={since_raw}")
    if project:
        filter_parts.append(f"project={project}")
    filter_ctx = f" ({', '.join(filter_parts)})" if filter_parts else ""

    # Ordering label depends on whether a topic was used for RRF ranking.
    order_label = "by relevance" if topic else "newest first"
    topic_ctx = f", topic={topic!r}" if topic else ""

    header = (
        f"kb_recent: {len(hits)} note(s) in knowledge base '{universe}'"
        f"{filter_ctx}{topic_ctx}, {order_label}\n"
    )
    blocks: list[str] = []
    for rank, hit in enumerate(hits, start=1):
        if hit.score != 0.0:
            score_line = f"    score: {hit.score:.4f}\n"
        else:
            score_line = "    score: n/a (ordered by time)\n"
        blocks.append(
            f"[{rank}] id={hit.id}\n"
            f"    title: {hit.title}\n"
            f"    type/project: {hit.type} / {hit.project}\n"
            f"    created_at: {hit.created_at.isoformat()}\n"
            f"{score_line}"
            f"    path: {hit.path}\n"
            f"    summary: {hit.summary}"
        )
    return header + "\n" + "\n\n".join(blocks)
