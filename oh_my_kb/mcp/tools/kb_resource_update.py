"""``kb_resource_update`` MCP tool — apply server updates to local resources.

Reuses ``_has_drift``, ``_write_resource``, and ``_regenerate_claude_md`` from the
CLI ``update_cmd`` module. No confirmation prompt — MCP callers get ``--yes`` semantics
by default.
"""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from oh_my_kb.cli.resource.manifest import (
    ResourceRecord,
    load_manifest,
    save_manifest,
)
from oh_my_kb.cli.resource.pull_cmd import _now_utc, _sha256_of
from oh_my_kb.cli.resource.registry import RESOURCE_REGISTRY
from oh_my_kb.cli.resource.update_cmd import _has_drift, _regenerate_claude_md, _write_resource

KB_RESOURCE_UPDATE_TOOL = Tool(
    name="kb_resource_update",
    description=(
        "Apply updates from the oh-my-kb server to the locally installed resources "
        "under ~/.claude/, update the manifest, and regenerate ~/.claude/CLAUDE.md. "
        "No confirmation is required — updates are applied immediately. "
        "Use when the user asks: 'atualize minhas skills do oh-my-kb', "
        "'quero a versao mais recente dos resources', "
        "'atualiza o template de nota', 'sincroniza meus resources', "
        "'update my oh-my-kb skills', 'sync my resources'. "
        "Accepts an optional 'resource' short_id to update only that resource; "
        "when omitted, all resources with drift are updated. "
        "Returns a per-resource report plus a summary line."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "resource": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Optional short_id of a single resource to update "
                    "(e.g. 'skills/scribe' or 'template'). "
                    "When omitted, all resources with drift are updated."
                ),
            },
        },
        "additionalProperties": False,
    },
)


async def handle_kb_resource_update(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Execute ``kb_resource_update``.

    Applies drift detection and writes resources without a confirmation prompt.
    Wraps every infrastructure call in try/except to keep the server alive.
    """
    resource_id: str | None = arguments.get("resource")

    manifest = load_manifest()
    if manifest is None:
        return [
            TextContent(
                type="text",
                text=(
                    "kb_resource_update: manifest nao encontrado em ~/.claude/.omk-manifest.json.\n"
                    "Execute omk resource pull --all para instalar os resources antes de atualizar."
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
                        f"kb_resource_update: resource '{resource_id}' nao encontrado.\n"
                        f"Resources disponiveis: {available}."
                    ),
                )
            ]
        targets = [meta]
    else:
        targets = list(RESOURCE_REGISTRY)

    report_lines: list[str] = []
    updated_count = 0
    unchanged_count = 0
    error_count = 0
    now = _now_utc()

    for meta in targets:
        try:
            has_drift, content, local_ver, server_ver = _has_drift(meta, manifest)
        except Exception as exc:
            report_lines.append(f"  x {meta.short_id:<22s}  erro ao verificar drift -- {exc}")
            error_count += 1
            continue

        if not has_drift:
            version_label = f" ({local_ver})" if local_ver else ""
            report_lines.append(
                f"  o {meta.short_id:<22s}  sem alteracoes{version_label}"
            )
            unchanged_count += 1
            continue

        try:
            _write_resource(meta, content)
        except Exception as exc:
            report_lines.append(f"  x {meta.short_id:<22s}  erro ao escrever -- {exc}")
            error_count += 1
            continue

        manifest.resources[meta.short_id] = ResourceRecord(
            uri=meta.uri,
            local_path=meta.local_path,
            content_version=server_ver,
            pulled_at=now,
            sha256=_sha256_of(content),
        )
        report_lines.append(
            f"  ok {meta.short_id:<22s}  atualizado  {local_ver} -> {server_ver}"
        )
        updated_count += 1

    if updated_count > 0:
        manifest.pulled_at = now
        try:
            save_manifest(manifest)
        except Exception as exc:
            report_lines.append(f"  x manifest: erro ao salvar -- {exc}")

        try:
            _regenerate_claude_md()
            report_lines.append("  ok ~/.claude/CLAUDE.md regenerado.")
        except Exception as exc:
            report_lines.append(
                f"  Aviso: ~/.claude/CLAUDE.md nao pode ser regenerado: {exc}. "
                "Execute omk install para corrigir."
            )

    # Summary line
    summary_parts: list[str] = []
    if updated_count:
        summary_parts.append(f"{updated_count} atualizado")
    if unchanged_count:
        summary_parts.append(f"{unchanged_count} sem alteracoes")
    if error_count:
        summary_parts.append(f"{error_count} erro(s)")
    summary = "  " + ", ".join(summary_parts) + "." if summary_parts else ""

    output = "\n".join(["", *report_lines, "", summary])
    return [TextContent(type="text", text=output)]
