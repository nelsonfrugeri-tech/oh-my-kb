"""``kb_resource_list`` MCP tool — list resources with local vs server version status.

Compares each resource's local version (from the manifest) with the server version
(from ``read_scribe_resource`` + ``_extract_content_version``). Works even when
the manifest is absent — treated as "never pulled" for each resource.
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from oh_my_kb.cli.resource.manifest import load_manifest
from oh_my_kb.cli.resource.pull_cmd import _extract_content_version, _sha256_of
from oh_my_kb.cli.resource.registry import RESOURCE_REGISTRY

KB_RESOURCE_LIST_TOOL = Tool(
    name="kb_resource_list",
    description=(
        "List all oh-my-kb resources available on the server and compare each one's "
        "local version (already installed) with the current server version. "
        "Use when the user asks: 'quais skills tenho instaladas', "
        "'meus resources estao atualizados', "
        "'lista o que o oh-my-kb tem disponivel', "
        "'show my installed skills', 'are my resources up to date'. "
        "Returns a status table showing local version, server version and "
        "a freshness marker for every resource, plus a count of outdated resources."
    ),
    inputSchema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)


async def handle_kb_resource_list(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Execute ``kb_resource_list``.

    Reads the manifest (if present) and the server content for each registry entry,
    then formats a status table. No Qdrant dependency.
    """
    from oh_my_kb.mcp.resources import read_scribe_resource

    try:
        manifest = load_manifest()
    except Exception as exc:
        return [
            TextContent(
                type="text",
                text=f"kb_resource_list: erro ao carregar manifest -- {exc}",
            )
        ]

    lines: list[str] = ["Resources disponiveis\n"]
    outdated_count = 0

    for meta in RESOURCE_REGISTRY:
        try:
            server_content = read_scribe_resource(meta.uri)
            server_version = _extract_content_version(server_content)
        except Exception as exc:
            lines.append(f"  {meta.short_id:<22s}  erro ao ler servidor: {exc}")
            continue

        if manifest is not None and meta.short_id in manifest.resources:
            record = manifest.resources[meta.short_id]
            local_version = record.content_version or "--"
            local_sha = record.sha256
        else:
            local_version = "--"
            local_sha = ""

        server_sha = _sha256_of(server_content)
        is_outdated = local_sha != server_sha

        if is_outdated:
            outdated_count += 1
            marker = "desatualizado"
        else:
            marker = "atualizado"

        lines.append(
            f"  {meta.short_id:<22s}  local: {local_version:<10s}  "
            f"servidor: {server_version:<10s}  {marker}"
        )

    lines.append("")
    if outdated_count == 0:
        lines.append("  Todos os resources estao atualizados.")
    else:
        lines.append(
            f"  {outdated_count} desatualizado(s). "
            "Use kb_resource_update para atualizar."
        )

    return [TextContent(type="text", text="\n".join(lines))]
