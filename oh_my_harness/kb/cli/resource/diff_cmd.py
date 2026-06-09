"""``omk resource diff`` — compare local resources with the MCP server version."""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

import typer

from oh_my_harness.kb.cli.resource.manifest import Manifest, load_manifest
from oh_my_harness.kb.cli.resource.pull_cmd import _extract_content_version
from oh_my_harness.kb.cli.resource.registry import RESOURCE_REGISTRY, ResourceMeta

_MANIFEST_MISSING_MSG = (
    "Erro: manifest não encontrado em ~/.claude/.omk-manifest.json.\n"
    "Execute omk resource pull --all para baixar os resources."
)


def _sha256_of(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _make_header(title: str, *, width: int = 80) -> str:
    """80-char box-drawing header using U+2500."""
    prefix = f"─── {title} "
    fill = max(0, width - len(prefix))
    return prefix + "─" * fill


def _diff_resource(
    meta: ResourceMeta,
    manifest: Manifest,
) -> tuple[bool, str]:
    """Compute diff for one resource. Returns (has_changes, formatted_block)."""
    from oh_my_harness.kb.mcp.resources import read_scribe_resource

    server_content = read_scribe_resource(meta.uri)
    server_sha = _sha256_of(server_content)
    server_version = _extract_content_version(server_content)

    local_record = manifest.resources.get(meta.short_id)
    local_version = local_record.content_version if local_record else ""
    local_sha = local_record.sha256 if local_record else ""

    if local_sha == server_sha:
        eq_marker = "=" if local_version == server_version else "?"
        title = (
            f"{meta.short_id}  "
            f"(local: {local_version} {eq_marker} servidor: {server_version})"
        )
        header = _make_header(title + " ─── sem alterações")
        return False, header

    # Read local file
    local_path_expanded = Path(meta.local_path).expanduser()
    try:
        local_content = local_path_expanded.read_text(encoding="utf-8")
    except FileNotFoundError:
        local_content = ""

    title = f"{meta.short_id}  (local: {local_version} → servidor: {server_version})"
    header = _make_header(title)

    local_lines = local_content.splitlines(keepends=True)
    server_lines = server_content.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            local_lines,
            server_lines,
            fromfile=f"local/{meta.short_id}",
            tofile=f"servidor/{meta.short_id}",
            lineterm="",
        )
    )

    colored_diff: list[str] = []
    for line in diff_lines:
        if line.startswith("+") and not line.startswith("+++"):
            colored_diff.append(f"\x1b[32m{line}\x1b[0m")
        elif line.startswith("-") and not line.startswith("---"):
            colored_diff.append(f"\x1b[31m{line}\x1b[0m")
        else:
            colored_diff.append(line)

    block = header + "\n\n" + "\n".join(colored_diff)
    return True, block


def diff_cmd(
    name: str | None = typer.Argument(
        None, help="Short resource name (e.g. 'skills/scribe')."
    ),
) -> None:
    """Compare local resources with the current server version (git-diff style)."""
    manifest = load_manifest()
    if manifest is None:
        typer.echo(_MANIFEST_MISSING_MSG)
        raise typer.Exit(code=1)

    if name is not None:
        meta = next((m for m in RESOURCE_REGISTRY if m.short_id == name), None)
        if meta is None:
            available = ", ".join(m.short_id for m in RESOURCE_REGISTRY)
            typer.echo(
                f"Erro: resource '{name}' não encontrado no servidor MCP.\n"
                f"Resources disponíveis: {available}."
            )
            raise typer.Exit(code=3)
        targets: list[ResourceMeta] = [meta]
    else:
        targets = list(RESOURCE_REGISTRY)

    changed_count = 0
    unchanged_count = 0
    blocks: list[str] = []

    for meta in targets:
        has_changes, block = _diff_resource(meta, manifest)
        blocks.append(block)
        if has_changes:
            changed_count += 1
        else:
            unchanged_count += 1

    if changed_count == 0 and name is None:
        typer.echo("Todos os resources estão atualizados.")
        return

    typer.echo("")
    for block in blocks:
        typer.echo(block)
        typer.echo("")

    if name is None:
        parts: list[str] = []
        if changed_count:
            parts.append(f"{changed_count} resource com alterações")
        if unchanged_count:
            parts.append(f"{unchanged_count} sem alterações")
        typer.echo(f"  {', '.join(parts)}.")
        if changed_count:
            typer.echo("  Para atualizar: omk resource update")
