"""``kb_write`` MCP tool — persist a fully-formed note via :class:`Indexer`.

Handlers are exposed as plain ``async def`` functions taking the dependency
(the :class:`Indexer`) plus the arguments dict, so tests can drive them
without spinning up a real MCP server. The server module wires them into
the :class:`Server` instance via a closure that captures the dependency.

The active universe is **server-bound** — taken from the server context, not
from the tool input — so the harness can't write into the wrong universe by
accident.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from mcp.types import TextContent, Tool
from pydantic import ValidationError

from oh_my_kb.core import Note, NoteType
from oh_my_kb.services import Indexer

KB_WRITE_TOOL = Tool(
    name="kb_write",
    description=(
        "Register a piece of knowledge — decision, event, procedure, "
        "reference or conversation — as a note in the active universe. "
        "Use when the user is recording something the team will want to "
        "look up later. The 'summary' field is the dense prose that gets "
        "indexed for similarity search; write it as a self-contained "
        "paragraph, not a label. The note is persisted as a .md file on "
        "disk and indexed in Qdrant."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1, "description": "Short title."},
            "type": {
                "type": "string",
                "enum": [t.value for t in NoteType],
                "description": (
                    "Closed enum: decision | event | procedure "
                    "| reference | conversation."
                ),
            },
            "project": {"type": "string", "minLength": 1, "description": "Project label."},
            "summary": {
                "type": "string",
                "minLength": 1,
                "description": "Dense prose; indexed for similarity search.",
            },
            "body": {"type": "string", "description": "Long-form markdown body."},
            "entities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Domain entities mentioned in the note.",
            },
            "links_out": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
                "description": "UUIDs of related notes this one links to.",
            },
            "supersedes": {
                "type": ["string", "null"],
                "format": "uuid",
                "description": "UUID of a note this one replaces (or null).",
            },
            "archived": {"type": "boolean", "description": "Mark as archived."},
        },
        "required": ["title", "type", "project", "summary"],
        "additionalProperties": False,
    },
)


async def handle_kb_write(
    indexer: Indexer,
    universe: str,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Execute ``kb_write`` against ``indexer`` (server-bound to ``universe``)."""
    try:
        note = _build_note(arguments, universe=universe)
    except (ValidationError, ValueError) as exc:
        return [TextContent(type="text", text=f"kb_write: invalid input — {exc}")]

    try:
        path = indexer.write_note(note)
    except Exception as exc:  # safety net so the server stays up
        return [TextContent(type="text", text=f"kb_write: indexer error — {exc}")]

    relative_path = path.relative_to(indexer._notes_root)
    body = (
        f"kb_write: wrote note\n"
        f"  id:      {note.id}\n"
        f"  slug:    {note.slug}\n"
        f"  path:    {relative_path}\n"
        f"  universe:{universe}"
    )
    return [TextContent(type="text", text=body)]


def _build_note(arguments: dict[str, Any], *, universe: str) -> Note:
    """Translate the raw tool input into a :class:`Note` (pydantic validates).

    Universe is injected from the server context — never from the input.
    """
    fields: dict[str, Any] = {
        "title": arguments["title"],
        "type": arguments["type"],
        "project": arguments["project"],
        "universe": universe,
        "summary": arguments["summary"],
    }
    if "body" in arguments:
        fields["body"] = arguments["body"]
    if "entities" in arguments:
        fields["entities"] = list(arguments["entities"])
    if "links_out" in arguments:
        fields["links_out"] = [UUID(s) for s in arguments["links_out"]]
    if arguments.get("supersedes") is not None:
        fields["supersedes"] = UUID(arguments["supersedes"])
    if "archived" in arguments:
        fields["archived"] = bool(arguments["archived"])
    return Note(**fields)
