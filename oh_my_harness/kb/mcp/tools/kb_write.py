"""``kb_write`` MCP tool — persist a fully-formed note via :class:`Indexer`.

Handlers are exposed as plain ``async def`` functions taking the dependency
(the :class:`Indexer`) plus the arguments dict, so tests can drive them
without spinning up a real MCP server. The server module wires them into
the :class:`Server` instance via a closure that captures the dependency.

The active knowledge base is **server-bound** — taken from the server context, not
from the tool input — so the harness can't write into the wrong knowledge base by
accident.
"""

from __future__ import annotations

import asyncio
from typing import Any, Final
from uuid import UUID

from mcp.types import TextContent, Tool
from pydantic import ValidationError

from oh_my_harness.kb.core import Note, NoteType
from oh_my_harness.kb.services import Indexer

# Light summary validation — the scribe skill defines *quality*; these
# constants define the *floor and ceiling* the kb_write boundary enforces
# so a careless caller can't accept a label-as-summary or a body-in-summary.
SUMMARY_MIN_LEN: Final[int] = 200
SUMMARY_MAX_LEN: Final[int] = 800

KB_WRITE_TOOL = Tool(
    name="kb_write",
    description=(
        "Register a piece of knowledge as a note in the active knowledge base. "
        "Call when recording a decision, event, procedure, reference, or "
        "conversation the user just made or described. The 'summary' field "
        "is the dense prose that gets indexed for similarity search; write "
        "it as a self-contained paragraph, not a label. The note is "
        "persisted as a .md file on disk and indexed in Qdrant. "
        "The knowledge base is server-bound — do not include it in the input."
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
                "oneOf": [
                    {"type": "string", "format": "uuid"},
                    {"type": "null"},
                ],
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
    summary_error = _validate_summary(
        title=str(arguments.get("title", "")),
        summary=str(arguments.get("summary", "")),
    )
    if summary_error is not None:
        return [TextContent(type="text", text=f"kb_write: invalid input — {summary_error}")]

    try:
        note = _build_note(arguments, universe=universe)
    except (ValidationError, ValueError) as exc:
        return [TextContent(type="text", text=f"kb_write: invalid input — {exc}")]

    try:
        # write_note calls BGEM3Embedder.embed_text (CPU/GPU-bound, ~50-500 ms).
        # Running in a thread pool keeps the event loop free for concurrent MCP
        # messages and the stdio keep-alive.
        result = await asyncio.to_thread(indexer.write_note, note)
    except Exception as exc:  # safety net so the server stays up
        return [TextContent(type="text", text=f"kb_write: indexer error — {exc}")]

    body = (
        f"kb_write: wrote note\n"
        f"  id:      {result.id}\n"
        f"  slug:    {result.slug}\n"
        f"  path:    {result.relative_path}\n"
        f"  kb:      {universe}"
    )
    return [TextContent(type="text", text=body)]


def _validate_summary(*, title: str, summary: str) -> str | None:
    """Return an error message if the summary violates the light rules.

    These checks live here (the kb_write boundary) rather than in
    :class:`Note` because they're MCP-tool-shape rules — the indexer must
    still accept short summaries written before this validation existed.
    The :class:`Note` model already rejects empty / whitespace-only
    summaries; this layer adds length-floor, length-ceiling and the
    title-not-equal-to-summary checks. See ``skill://scribe/SKILL.md``
    for the rationale.
    """
    stripped = summary.strip()
    if not stripped:
        return "summary must not be empty or whitespace"
    if stripped == title.strip():
        return "summary must not be identical to the title"
    length = len(stripped)
    if length < SUMMARY_MIN_LEN:
        return (
            f"summary is too short ({length} chars); minimum is "
            f"{SUMMARY_MIN_LEN}. Read skill://scribe/SKILL.md for examples."
        )
    if length > SUMMARY_MAX_LEN:
        return (
            f"summary is too long ({length} chars); maximum is "
            f"{SUMMARY_MAX_LEN}. The body field is for long-form content."
        )
    return None


def _build_note(arguments: dict[str, Any], *, universe: str) -> Note:
    """Translate the raw tool input into a :class:`Note` (pydantic validates).

    Knowledge base name is injected from the server context — never from the input.
    """
    fields: dict[str, Any] = {
        "title": arguments["title"],
        "type": arguments["type"],
        "project": arguments["project"],
        "kb_name": universe,
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
