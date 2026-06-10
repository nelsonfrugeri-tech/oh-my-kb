"""``omk resource update`` — apply server updates to local resources."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import typer

from oh_my_harness.kb.cli.resource.manifest import (
    Manifest,
    ResourceRecord,
    load_manifest,
    save_manifest,
)
from oh_my_harness.kb.cli.resource.pull_cmd import _extract_content_version
from oh_my_harness.kb.cli.resource.registry import RESOURCE_REGISTRY, ResourceMeta

_MANIFEST_MISSING_MSG = (
    "Erro: manifest não encontrado em ~/.claude/.omk-manifest.json.\n"
    "Execute omk resource pull --all para instalar os resources antes de atualizar."
)


def _sha256_of(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _server_content(meta: ResourceMeta) -> str:
    from oh_my_harness.kb.mcp.resources import read_scribe_resource

    return read_scribe_resource(meta.uri)


def _has_drift(
    meta: ResourceMeta, manifest: Manifest
) -> tuple[bool, str, str, str]:
    """Return (has_drift, server_content, local_version, server_version)."""
    content = _server_content(meta)
    server_sha = _sha256_of(content)
    server_version = _extract_content_version(content)
    local_record = manifest.resources.get(meta.short_id)
    local_sha = local_record.sha256 if local_record else ""
    local_version = local_record.content_version if local_record else ""
    return local_sha != server_sha, content, local_version, server_version


def _write_resource(
    meta: ResourceMeta, content: str, home: Path | None = None
) -> Path:
    """Write content to the local path, creating parent dirs if needed."""
    if home is not None:
        rel = meta.local_path.replace("~/", "")
        dest = home / rel
    else:
        dest = Path(meta.local_path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


def _regenerate_claude_md(home: Path | None = None) -> None:
    """Regenerate ~/.claude/CLAUDE.md via do_bootstrap (best-effort)."""
    from oh_my_harness.kb.agents.bootstrap import do_bootstrap
    from oh_my_harness.kb.cli.config import load_config, load_omk_config

    omk_cfg = load_omk_config()
    harness = omk_cfg.harness.active

    cli_cfg = load_config()
    universe = cli_cfg.active or "default"

    typer.echo("  Regenerando ~/.claude/CLAUDE.md...")
    try:
        do_bootstrap(harness, universe, home=home)
        typer.echo("  ✓ ~/.claude/CLAUDE.md atualizado.")
    except Exception as exc:
        typer.echo(
            f"  Aviso: ~/.claude/CLAUDE.md não pôde ser regenerado: {exc}. "
            "Execute omk install para corrigir."
        )


def update_cmd(
    name: str | None = typer.Argument(
        None, help="Short resource name (e.g. 'skills/scribe')."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts."
    ),
) -> None:
    """Apply updates from the server to local resources and regenerate CLAUDE.md."""
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

    drift_results: list[tuple[ResourceMeta, bool, str, str, str]] = []
    for meta in targets:
        has_drift, content, local_ver, server_ver = _has_drift(meta, manifest)
        drift_results.append((meta, has_drift, content, local_ver, server_ver))

    changed = [
        (m, c, lv, sv) for m, d, c, lv, sv in drift_results if d
    ]
    unchanged = [(m, lv) for m, d, c, lv, sv in drift_results if not d]

    # Single resource already up-to-date
    if name is not None and not changed:
        local_version = unchanged[0][1] if unchanged else ""
        suffix = f" ({local_version})." if local_version else "."
        typer.echo(f"○ {name} já está na versão mais recente{suffix}")
        return

    # All up-to-date
    if not changed:
        typer.echo("Todos os resources já estão na versão mais recente.")
        return

    # Print summary
    typer.echo("")
    typer.echo(f"  {len(changed)} resource com alterações:\n")
    for meta, _, local_ver, server_ver in changed:
        typer.echo(f"  ● {meta.short_id}  ({local_ver} → {server_ver})")
    for meta, _local_ver in unchanged:
        typer.echo(f"  ○ {meta.short_id}       sem alterações")
    typer.echo("")

    updated_count = 0
    now = _now_utc()

    for meta, content, _local_ver, server_ver in changed:
        if not yes:
            confirmed = typer.confirm(
                f"  Atualizar {meta.short_id}?", default=False
            )
            if not confirmed:
                continue

        _write_resource(meta, content)
        typer.echo(
            f"  ✓ {meta.short_id}  →  {meta.local_path}  "
            f"(atualizado para {server_ver})"
        )

        manifest.resources[meta.short_id] = ResourceRecord(
            uri=meta.uri,
            local_path=meta.local_path,
            content_version=server_ver,
            pulled_at=now,
            sha256=_sha256_of(content),
        )
        updated_count += 1

    if updated_count == 0:
        return

    manifest.pulled_at = now
    save_manifest(manifest)

    typer.echo("")
    _regenerate_claude_md()

    typer.echo("")
    skipped = len(changed) - updated_count
    parts: list[str] = [f"  {updated_count} atualizado"]
    if unchanged:
        parts.append(f"{len(unchanged)} sem alterações")
    if skipped:
        parts.append(f"{skipped} ignorado(s)")
    typer.echo(", ".join(parts) + ".")
