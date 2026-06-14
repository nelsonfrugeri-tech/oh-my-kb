"""``kb_tree`` MCP tool — project-grouped directory of note summaries.

The handler is a thin adapter over :class:`NavigationService.get_tree`. It
calls the service inline (no ``asyncio.to_thread``) because ``get_tree`` only
reads Qdrant payloads — no filesystem I/O, no CPU-bound embedding — so it
will not block the event loop meaningfully.
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from oh_my_harness.kb.services import NavigationService, TreeNode

KB_TREE_TOOL = Tool(
    name="kb_tree",
    description=(
        "Map the active knowledge base as a project-grouped directory of note summaries. "
        "Use when the question is about what *exists* or what *relates* "
        "('what notes are in project X?', 'what topics does this knowledge base cover?'), "
        "or when you need ids to feed into kb_expand. "
        "Do *not* use for semantic similarity queries — that is kb_search. "
        "Returns summaries only, never full body; call kb_expand on any id to read a note completely."  # noqa: E501
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "minLength": 1,
                "description": "Optional project filter (non-empty when provided).",
            },
            "include_archived": {
                "type": "boolean",
                "default": False,
                "description": "Include archived notes in the tree.",
            },
        },
        "additionalProperties": False,
    },
)


async def handle_kb_tree(
    navigation: NavigationService,
    universe: str,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Execute ``kb_tree`` against ``navigation`` (server-bound to ``universe``).

    ``get_tree`` is pure Qdrant scroll — no embedding, no filesystem I/O —
    so it is called inline without ``asyncio.to_thread``.
    """
    project: str | None = arguments.get("project")
    include_archived: bool = bool(arguments.get("include_archived", False))

    try:
        tree = navigation.get_tree(
            universe,
            project=project,
            include_archived=include_archived,
        )
    except Exception as exc:  # keep the server alive on infrastructure errors
        return [TextContent(type="text", text=f"kb_tree: navigation error — {exc}")]

    if not tree:
        return [TextContent(type="text", text=_format_empty(universe, project))]

    total = sum(len(nodes) for nodes in tree.values())
    return [TextContent(type="text", text=_format_tree(tree, universe, project, total))]


def _format_empty(universe: str, project: str | None) -> str:
    if project:
        return (
            f"kb_tree: no notes found in knowledge base '{universe}' (project={project}).\n"
            "Use kb_write to start recording notes, or remove the project filter to see all projects."  # noqa: E501
        )
    return (
        f"kb_tree: knowledge base '{universe}' has no notes yet.\n"
        "Use kb_write to start recording notes."
    )


def _format_tree(
    tree: dict[str, list[TreeNode]],
    universe: str,
    project: str | None,
    total: int,
) -> str:
    project_suffix = f" (project={project})" if project else ""
    header = f"kb_tree: {total} note(s) in knowledge base '{universe}'{project_suffix}"

    blocks: list[str] = [header]
    for proj, nodes in sorted(tree.items()):
        blocks.append(f"\n=== {proj} ===\n")
        for node in nodes:
            blocks.append(
                f"id={node.id}\n"
                f"  title:    {node.title}\n"
                f"  type:     {node.type}\n"
                f"  summary:  {node.summary}"
            )

    return "\n".join(blocks)
