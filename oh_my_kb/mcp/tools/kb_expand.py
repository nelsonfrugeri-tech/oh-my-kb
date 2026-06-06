"""``kb_expand`` MCP tool — full note content with resolved outbound links.

The handler is a thin adapter over :class:`NavigationService.expand`. It uses
``asyncio.to_thread`` because ``expand`` calls ``Indexer.read_note_by_id``
which does filesystem I/O — consistent with how ``kb_write`` and ``kb_search``
handle their blocking operations.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from mcp.types import TextContent, Tool

from oh_my_kb.services import ExpandResult, NavigationService, NoteNotFoundError, ResolvedLink

KB_EXPAND_TOOL = Tool(
    name="kb_expand",
    description=(
        "Read a note in full (title, metadata, complete body) and reveal its outbound links "
        "as a resolved list (id, title, type, summary). "
        "Use when a summary from kb_search or kb_tree is not enough, or to follow the knowledge "
        "graph hop by hop: call kb_expand again on any link id returned here. "
        "The id to pass comes from a prior kb_search hit, kb_tree row, or kb_expand link. "
        "Do *not* use when you only need summaries — kb_tree is faster for an overview."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the note to expand.",
            },
        },
        "required": ["id"],
        "additionalProperties": False,
    },
)


async def handle_kb_expand(
    navigation: NavigationService,
    universe: str,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Execute ``kb_expand`` against ``navigation`` (server-bound to ``universe``).

    ``expand`` calls ``Indexer.read_note_by_id`` which reads the .md file from
    disk; running it in a thread pool keeps the event loop free for concurrent
    MCP messages and the stdio keep-alive.
    """
    raw_id: str = arguments.get("id", "")

    try:
        note_id = UUID(raw_id)
    except ValueError:
        return [
            TextContent(
                type="text",
                text="kb_expand: invalid input — id is not a valid UUID.",
            )
        ]

    try:
        result: ExpandResult = await asyncio.to_thread(
            navigation.expand, note_id, universe
        )
    except NoteNotFoundError:
        return [
            TextContent(
                type="text",
                text=(
                    f"kb_expand: note '{raw_id}' not found in universe '{universe}'.\n"
                    "Use kb_tree to list valid ids, or kb_search to find notes by content."
                ),
            )
        ]
    except Exception as exc:  # keep the server alive on infrastructure errors
        return [TextContent(type="text", text=f"kb_expand: navigation error — {exc}")]

    return [TextContent(type="text", text=_format_result(result))]


def _format_result(result: ExpandResult) -> str:
    note = result.note
    note_id = str(note.id)

    header = (
        f"kb_expand: note {note_id}\n"
        f"\n"
        f"  title:      {note.title}\n"
        f"  type:       {note.type.value if hasattr(note.type, 'value') else note.type}\n"
        f"  project:    {note.project}\n"
        f"  created_at: {note.created_at.isoformat()}\n"
        f"  summary:    {note.summary}"
    )

    body_section = f"\n--- body ---\n{note.body}\n--- end body ---"

    links_section = _format_links(result.links)

    return f"{header}{body_section}\n{links_section}"


def _format_links(links: list[ResolvedLink]) -> str:
    if not links:
        return "--- links out ---\nno links out — terminal note.\n--- end links ---"

    count = len(links)
    parts: list[str] = [f"--- links out ({count}) ---\n"]
    for link in links:
        parts.append(
            f"id={link.id}\n"
            f"  title:    {link.title}\n"
            f"  type:     {link.type}\n"
            f"  summary:  {link.summary}"
        )
    parts.append("--- end links ---")
    return "\n".join(parts)
