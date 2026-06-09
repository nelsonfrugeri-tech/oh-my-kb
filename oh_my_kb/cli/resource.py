"""``omk resource`` sub-commands.

Provides list, pull, diff, and update for MCP resources.

Resources are served by the local MCP server but, because the server and the
CLI share the same package, we call the Python layer directly instead of
speaking the MCP stdio protocol — this avoids any external process dependency
while keeping the semantics identical.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import typer
from rich.console import Console

from oh_my_kb.cli.manifest import (
    Manifest,
    load_manifest,
    save_manifest,
    upsert_entry,
)
from oh_my_kb.mcp.resources import (
    _URI_TO_RESOURCE_ID,
    compute_sha256,
    list_scribe_resources,
    read_scribe_resource,
)

app = typer.Typer(
    help="List, pull, diff and update MCP resources to ~/.claude/.",
    no_args_is_help=True,
)

console = Console()

# Reverse mapping: URI → CLI resource_id
_URI_TO_ID: dict[str, str] = _URI_TO_RESOURCE_ID

# Forward mapping: resource_id → URI (built at module load)
_ID_TO_URI: dict[str, str] = {v: k for k, v in _URI_TO_RESOURCE_ID.items()}

# resource_id → local_path with ~ (not expanded)
_ID_TO_LOCAL_PATH: dict[str, str] = {
    "skills/scribe": "~/.claude/skills/scribe/SKILL.md",
    "skills/scribe-template": "~/.claude/skills/scribe/template.md",
}

_SECTION_WIDTH = 80


def _section_header(title: str) -> str:
    """Build a section header line 80 chars wide using box-drawing dashes."""
    padding = max(0, _SECTION_WIDTH - 5 - len(title))
    return f"─── {title} " + "─" * padding


def _all_server_resources() -> list[dict[str, str]]:
    """Return list of dicts with keys: resource_id, uri, content_version, sha256."""
    try:
        resources = list_scribe_resources()
    except Exception as exc:
        typer.secho(
            "  Erro: não foi possível conectar ao servidor MCP.\n"
            "  Verifique se o servidor está rodando com omk status.",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    result = []
    for r in resources:
        annotations = r.annotations
        if annotations is None:
            resource_id = _URI_TO_ID.get(str(r.uri), str(r.uri))
            content_version = "0.0.0"
            sha256 = ""
        else:
            extra = annotations.model_extra or {}
            resource_id = extra.get("resource_id", _URI_TO_ID.get(str(r.uri), str(r.uri)))
            content_version = extra.get("content_version", "0.0.0")
            sha256 = extra.get("sha256", "")
        result.append(
            {
                "resource_id": resource_id,
                "uri": str(r.uri),
                "content_version": content_version,
                "sha256": sha256,
                "name": r.name,
            }
        )
    return result


def _local_path_for(resource_id: str) -> Path:
    """Return the expanded local path for a resource.

    Uses ``Path.home()`` directly (not ``os.path.expanduser``) so that test
    fixtures that monkeypatch ``Path.home`` are respected.
    """
    tilde = _ID_TO_LOCAL_PATH.get(resource_id)
    if tilde is None:
        return Path.home() / ".claude" / resource_id
    if tilde.startswith("~/.claude/"):
        # Replace the "~/.claude/" prefix with Path.home() / ".claude"
        rest = tilde[len("~/.claude/"):]
        return Path.home() / ".claude" / rest
    return Path(tilde).expanduser()


def _write_resource_to_disk(resource_id: str, content: str) -> Path:
    """Write resource content to the canonical local path and return it."""
    dest = _local_path_for(resource_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.write_text(content, encoding="utf-8")
    except PermissionError as exc:
        typer.secho(
            "  Erro: sem permissão para escrever em ~/.claude/.\n"
            "  Verifique as permissões do diretório.",
            err=True,
        )
        raise typer.Exit(code=4) from exc
    return dest


# ---------------------------------------------------------------------------
# omk resource list
# ---------------------------------------------------------------------------


@app.command("list")
def list_cmd() -> None:
    """List all resources available on the MCP server."""
    resources = _all_server_resources()

    typer.echo("")
    typer.echo("  Resources disponíveis no servidor MCP")
    typer.echo("")

    max_id = max((len(r["resource_id"]) for r in resources), default=10)
    max_uri = max((len(r["uri"]) for r in resources), default=30)

    for r in resources:
        local = _ID_TO_LOCAL_PATH.get(r["resource_id"], "~/.claude/" + r["resource_id"])
        typer.echo(
            f"  {r['resource_id']:<{max_id}}  "
            f"{r['uri']:<{max_uri}}  →  {local}"
            f"  (v{r['content_version']})"
        )

    typer.echo("")
    count = len(resources)
    suffix = "s" if count != 1 else ""
    typer.echo(f"  {count} resource{suffix} encontrado{suffix}.")
    typer.echo("")


# ---------------------------------------------------------------------------
# omk resource pull
# ---------------------------------------------------------------------------


@app.command("pull")
def pull_cmd(
    resource: str | None = typer.Argument(
        None,
        help="Resource ID to pull (e.g. skills/scribe). Omit when using --all.",
    ),
    all_: bool = typer.Option(
        False,
        "--all",
        help="Pull all available resources.",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        help="Print resource content to stdout without saving.",
    ),
) -> None:
    """Pull one or all resources from the MCP server to ~/.claude/."""
    if not resource and not all_:
        typer.secho(
            "  Erro: forneça um resource ID ou use --all.",
            err=True,
        )
        raise typer.Exit(code=1)

    server_resources = _all_server_resources()
    server_by_id = {r["resource_id"]: r for r in server_resources}

    targets: list[dict[str, str]]
    if all_:
        targets = server_resources
    else:
        if resource not in server_by_id:
            typer.secho(
                f"  Erro: resource '{resource}' não encontrado no servidor MCP.",
                err=True,
            )
            raise typer.Exit(code=3)
        targets = [server_by_id[resource]]

    # Load or create manifest
    try:
        manifest = load_manifest()
    except FileNotFoundError:
        manifest = Manifest()

    pulled = 0
    for r in targets:
        resource_id = r["resource_id"]
        uri = r["uri"]
        content_version = r["content_version"]

        content = read_scribe_resource(uri)
        sha256 = compute_sha256(content)

        if stdout:
            typer.echo(content)
            continue

        dest = _write_resource_to_disk(resource_id, content)
        size_kb = len(content.encode("utf-8")) / 1024
        local_path_tilde = _ID_TO_LOCAL_PATH.get(resource_id, str(dest))

        upsert_entry(
            manifest=manifest,
            resource_id=resource_id,
            uri=uri,
            local_path=local_path_tilde,
            content_version=content_version,
            sha256=sha256,
        )

        typer.secho(
            f"  ✓ {resource_id:<30}  →  {local_path_tilde}  ({size_kb:.1f} KB)",
            fg=typer.colors.GREEN,
        )
        pulled += 1

    if not stdout:
        save_manifest(manifest)
        typer.echo("")
        p_suffix = "s" if pulled != 1 else ""
        typer.echo(f"  {pulled} resource{p_suffix} baixado{p_suffix} para ~/.claude/")
        typer.echo("")


# ---------------------------------------------------------------------------
# omk resource diff
# ---------------------------------------------------------------------------


@app.command("diff")
def diff_cmd(
    resource: str | None = typer.Argument(
        None,
        help="Resource ID to diff. Omit to diff all.",
    ),
) -> None:
    """Show differences between local manifest and server versions."""
    # --- load manifest ---
    try:
        manifest = load_manifest()
    except FileNotFoundError as exc:
        typer.secho(
            "  Erro: manifest não encontrado em ~/.claude/.omk-manifest.json.\n"
            "  Execute omk resource pull --all para baixar os resources.",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    all_server_resources = _all_server_resources()
    all_server_ids = {r["resource_id"] for r in all_server_resources}

    if resource:
        server_resources = [r for r in all_server_resources if r["resource_id"] == resource]
        if not server_resources:
            typer.secho(
                f"  Erro: resource '{resource}' não encontrado no servidor MCP.",
                err=True,
            )
            raise typer.Exit(code=3)
    else:
        server_resources = all_server_resources

    # Warn about resources removed from server but still in manifest
    for rid in list(manifest.resources.keys()):
        if rid not in all_server_ids:
            typer.secho(
                f"  Aviso: '{rid}' está no manifest local mas não existe mais no servidor. "
                "Execute omk resource pull --all para sincronizar o manifest.",
                err=True,
            )

    changed_count = 0
    unchanged_count = 0
    any_output = False

    for r in server_resources:
        resource_id = r["resource_id"]
        uri = r["uri"]
        server_version = r["content_version"]
        server_sha256 = r["sha256"]

        entry = manifest.resources.get(resource_id)

        if entry is None:
            # Not in manifest — treat as changed (version "none")
            local_version = "none"
            is_changed = True
        elif entry.sha256 == server_sha256:
            local_version = entry.content_version
            is_changed = False
        else:
            local_version = entry.content_version
            is_changed = True

        if is_changed:
            changed_count += 1
            title = f"{resource_id}  (local: {local_version}  →  servidor: {server_version})"
            console.print(_section_header(title))

            # Compute actual text diff
            local_path = _local_path_for(resource_id)
            local_text = ""
            if local_path.exists():
                local_text = local_path.read_text(encoding="utf-8")
            server_text = read_scribe_resource(uri)

            diff_lines = list(
                difflib.unified_diff(
                    local_text.splitlines(keepends=True),
                    server_text.splitlines(keepends=True),
                    fromfile=f"local/{resource_id}",
                    tofile=f"server/{resource_id}",
                    lineterm="",
                )
            )
            for line in diff_lines:
                if line.startswith("+") and not line.startswith("+++"):
                    console.print(f"[green]{line}[/green]")
                elif line.startswith("-") and not line.startswith("---"):
                    console.print(f"[red]{line}[/red]")
                elif line.startswith("@@"):
                    console.print(f"[cyan]{line}[/cyan]")
                else:
                    console.print(line)
            any_output = True
        else:
            unchanged_count += 1
            title = f"{resource_id}  (local: {local_version}  =  servidor: {server_version})"
            console.print(
                _section_header(title) + " sem alterações ───"
            )
            any_output = True

    if not any_output or (changed_count == 0 and unchanged_count == 0):
        typer.echo("  Todos os resources estão atualizados.")
        return

    typer.echo("")
    if changed_count == 0:
        typer.echo("  Todos os resources estão atualizados.")
    else:
        changed_word = "resource" if changed_count == 1 else "resources"
        typer.echo(
            f"  {changed_count} {changed_word} com alterações, "
            f"{unchanged_count} sem alterações."
        )
        typer.echo("  Para atualizar: omk resource update")


# ---------------------------------------------------------------------------
# omk resource update
# ---------------------------------------------------------------------------


@app.command("update")
def update_cmd(
    resource: str | None = typer.Argument(
        None,
        help="Resource ID to update. Omit to check and update all.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Apply all updates without per-resource confirmation.",
    ),
) -> None:
    """Update local resources to server versions, then regenerate CLAUDE.md."""
    # --- load manifest ---
    try:
        manifest = load_manifest()
    except FileNotFoundError as exc:
        typer.secho(
            "  Erro: manifest não encontrado em ~/.claude/.omk-manifest.json.\n"
            "  Execute omk resource pull --all para baixar os resources.",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    all_server_resources = _all_server_resources()
    all_server_ids = {r["resource_id"] for r in all_server_resources}

    if resource:
        server_resources = [r for r in all_server_resources if r["resource_id"] == resource]
        if not server_resources:
            typer.secho(
                f"  Erro: resource '{resource}' não encontrado no servidor MCP.",
                err=True,
            )
            raise typer.Exit(code=3)
    else:
        server_resources = all_server_resources

    # Warn about resources removed from server but still in manifest
    for rid in list(manifest.resources.keys()):
        if rid not in all_server_ids:
            typer.secho(
                f"  Aviso: '{rid}' está no manifest local mas não existe mais no servidor. "
                "Execute omk resource pull --all para sincronizar o manifest.",
                err=True,
            )

    # Classify resources
    changed: list[dict[str, str]] = []
    unchanged: list[dict[str, str]] = []

    for r in server_resources:
        resource_id = r["resource_id"]
        server_sha256 = r["sha256"]
        entry = manifest.resources.get(resource_id)
        if entry is None or entry.sha256 != server_sha256:
            changed.append(r)
        else:
            unchanged.append(r)

    # Special case: single resource explicitly requested and already up to date
    if resource and not changed:
        r = unchanged[0] if unchanged else server_resources[0]
        entry = manifest.resources.get(r["resource_id"])
        current_version = entry.content_version if entry else r["content_version"]
        typer.echo(
            f"  ○ {r['resource_id']} já está na versão mais recente ({current_version})."
        )
        return

    # Print summary
    typer.echo("")
    total_changed = len(changed)
    if total_changed == 0:
        typer.echo("  Todos os resources estão atualizados.")
        return

    typer.echo(f"  {total_changed} resource{'s' if total_changed != 1 else ''} com alterações:")
    typer.echo("")
    for r in changed:
        resource_id = r["resource_id"]
        entry = manifest.resources.get(resource_id)
        local_ver = entry.content_version if entry else "none"
        server_ver = r["content_version"]
        typer.echo(f"  ● {resource_id}  ({local_ver} → {server_ver})")
    for r in unchanged:
        typer.echo(f"  ○ {r['resource_id']}  sem alterações")
    typer.echo("")

    # Apply updates
    updated_count = 0
    skipped_count = 0

    for r in changed:
        resource_id = r["resource_id"]
        uri = r["uri"]
        server_version = r["content_version"]
        entry = manifest.resources.get(resource_id)
        local_ver = entry.content_version if entry else "none"
        local_path_tilde = _ID_TO_LOCAL_PATH.get(resource_id, "~/.claude/" + resource_id)

        if not yes:
            answer = typer.prompt(
                f"  Atualizar {resource_id}? [s/N]",
                default="N",
                show_default=False,
            )
            if answer.strip().lower() not in ("s", "sim"):
                skipped_count += 1
                continue

        content = read_scribe_resource(uri)
        sha256 = compute_sha256(content)
        _write_resource_to_disk(resource_id, content)

        upsert_entry(
            manifest=manifest,
            resource_id=resource_id,
            uri=uri,
            local_path=local_path_tilde,
            content_version=server_version,
            sha256=sha256,
        )

        typer.secho(
            f"  ✓ {resource_id}  →  {local_path_tilde}  (atualizado para {server_version})",
            fg=typer.colors.GREEN,
        )
        updated_count += 1

    if updated_count > 0:
        save_manifest(manifest)

        # --- Regenerate CLAUDE.md ---
        _do_regenerate_claude_md()

    # Final summary
    typer.echo("")
    parts = []
    if updated_count > 0:
        parts.append(
            f"{updated_count} atualizado{'s' if updated_count != 1 else ''}"
        )
    skip_total = skipped_count + len(unchanged)
    if skip_total > 0:
        parts.append(
            f"{skip_total} sem alterações"
        )
    typer.echo("  " + ", ".join(parts) + ".")


def _do_regenerate_claude_md() -> None:
    """Regenerate ~/.claude/CLAUDE.md via do_bootstrap(); best-effort."""
    from oh_my_kb.agents.bootstrap import do_bootstrap
    from oh_my_kb.cli.config import load_config, load_omk_config

    typer.echo("")
    typer.echo("  Regenerando ~/.claude/CLAUDE.md...")
    try:
        omk_cfg = load_omk_config()
        cli_cfg = load_config()
        harness = omk_cfg.harness.active
        universe = cli_cfg.active
        if universe is None:
            raise ValueError("no active universe configured")
        do_bootstrap(harness, universe)
        typer.secho(
            "  ✓ ~/.claude/CLAUDE.md atualizado.",
            fg=typer.colors.GREEN,
        )
    except Exception as exc:
        typer.secho(
            f"  Aviso: resources atualizados mas ~/.claude/CLAUDE.md não pôde "
            f"ser regenerado: {exc}.\n"
            "  Rode omk install para corrigir.",
            err=True,
        )
