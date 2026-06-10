"""``kb_resource_diff`` MCP tool — diff local resources against the server version.

Reuses ``_diff_resource`` from the CLI ``diff_cmd`` module to produce unified-diff
output matching the ``omk resource diff`` command, without invoking typer.
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from oh_my_kb.cli.resource.diff_cmd import _diff_resource
from oh_my_kb.cli.resource.manifest import load_manifest
from oh_my_kb.cli.resource.registry import RESOURCE_REGISTRY

KB_RESOURCE_DIFF_TOOL = Tool(
    name="kb_resource_diff",
    description=(
        "Show a git-style unified diff between the locally installed version of "
        "oh-my-kb resources and the current server version. "
        "Use when the user asks: 'o que mudou nas minhas skills', "
        "'tem algo novo no oh-my-kb', 'mostra o diff dos resources', "
        "'what changed in my resources', 'show resource diff'. "
        "Accepts an optional 'resource' short_id to diff a single resource; "
        "when omitted, diffs all resources. "
        "Returns the unified diff blocks plus a summary (N com alterações, M sem alterações)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "resource": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Optional short_id of a single resource to diff "
                    "(e.g. 'skills/scribe' or 'template'). "
                    "When omitted, all resources are diffed."
                ),
            },
        },
        "additionalProperties": False,
    },
)


async def handle_kb_resource_diff(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Execute ``kb_resource_diff``.

    Delegates diff computation to ``_diff_resource`` from the CLI layer.
    """
    resource_id: str | None = arguments.get("resource")

    manifest = load_manifest()
    if manifest is None:
        return [
            TextContent(
                type="text",
                text=(
                    "kb_resource_diff: manifest não encontrado em ~/.claude/.omk-manifest.json.\n"
                    "Execute omk resource pull --all para baixar os resources primeiro."
                ),
            )
        ]

    if resource_id is not None:
        meta = next(
            (m for m in RESOURCE_REGISTRY if m.short_id == resource_id), None
        )
        if meta is None:
            available = ", ".join(m.short_id for m in RESOURCE_REGISTRY)
            return [
                TextContent(
                    type="text",
                    text=(
                        f"kb_resource_diff: resource '{resource_id}' não encontrado.\n"
                        f"Resources disponíveis: {available}."
                    ),
                )
            ]
        targets = [meta]
    else:
        targets = list(RESOURCE_REGISTRY)

    changed_count = 0
    unchanged_count = 0
    blocks: list[str] = []

    for meta in targets:
        try:
            has_changes, block = _diff_resource(meta, manifest)
        except Exception as exc:
            blocks.append(f"  {meta.short_id}: erro ao calcular diff — {exc}")
            continue
        blocks.append(block)
        if has_changes:
            changed_count += 1
        else:
            unchanged_count += 1

    parts: list[str] = []
    if changed_count:
        parts.append(f"{changed_count} resource com alterações")
    if unchanged_count:
        parts.append(f"{unchanged_count} sem alterações")
    summary = "  " + ", ".join(parts) + "." if parts else ""

    output_parts = ["", *blocks, "", summary]
    return [TextContent(type="text", text="\n".join(output_parts))]
