"""``omh agents`` — manage agents from the remote manifest."""

from __future__ import annotations

from typing import Annotated

import typer

from oh_my_harness.kb.cli._remote import load_remote_manifest
from oh_my_harness.kb.cli.agents._ops import (
    agent_status,
    agents_dest_root,
    local_version,
    pull_agent,
)

agents_app = typer.Typer(
    help="Manage agents from the official manifest.",
    no_args_is_help=True,
)


@agents_app.command("list")
def list_cmd() -> None:
    """List agents with local and remote version and status."""
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = agents_dest_root()
    header = f"{'AGENT':<22}  {'LOCAL':<10}  {'REMOTE':<10}  STATUS"
    typer.echo(header)
    typer.echo("-" * len(header))
    for entry in manifest.agents:
        loc = local_version(entry, dest)
        status = agent_status(entry, dest)
        typer.echo(f"{entry.name:<22}  {loc:<10}  {entry.version:<10}  {status}")


@agents_app.command("pull")
def pull_cmd(
    name: Annotated[str | None, typer.Argument(help="Agent name to pull.")] = None,
    all_agents: Annotated[bool, typer.Option("--all", help="Pull all agents.")] = False,
) -> None:
    """Download agent(s) to ~/.claude/agents/."""
    if not name and not all_agents:
        typer.secho("provide an agent name or --all", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = agents_dest_root()

    if all_agents:
        for entry in manifest.agents:
            try:
                pull_agent(entry, dest)
                typer.secho(f"  pulled {entry.name}", fg=typer.colors.GREEN)
            except RuntimeError as exc:
                typer.secho(f"  warning: {entry.name}: {exc}", fg=typer.colors.YELLOW, err=True)
        return

    entry_map = {e.name: e for e in manifest.agents}
    if name not in entry_map:
        typer.secho(
            f"error: agent '{name}' not found in manifest", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)
    try:
        pull_agent(entry_map[name], dest)
        typer.secho(f"  pulled {name}", fg=typer.colors.GREEN)
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@agents_app.command("diff")
def diff_cmd(
    name: Annotated[str | None, typer.Argument(help="Agent name to diff.")] = None,
) -> None:
    """Compare local sha256 vs remote for agent(s)."""
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = agents_dest_root()
    entries = manifest.agents
    if name:
        entries = [e for e in entries if e.name == name]
        if not entries:
            typer.secho(
                f"error: agent '{name}' not found in manifest",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

    header = f"{'AGENT':<22}  {'LOCAL':<10}  {'REMOTE':<10}  STATUS"
    typer.echo(header)
    typer.echo("-" * len(header))
    for entry in entries:
        loc = local_version(entry, dest)
        status = agent_status(entry, dest)
        line = f"{entry.name:<22}  {loc:<10}  {entry.version:<10}  {status}"
        if status == "drift" and loc not in ("(none)", "--"):
            try:
                local_major = int(loc.split(".")[0])
                remote_major = int(entry.version.split(".")[0])
                if remote_major > local_major:
                    line += "  [BREAKING]"
            except (ValueError, IndexError):
                pass
        typer.echo(line)


@agents_app.command("update")
def update_cmd(
    name: Annotated[str | None, typer.Argument(help="Agent name to update.")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Update agent(s) that are not up-to-date."""
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = agents_dest_root()
    entries = manifest.agents
    if name:
        entries = [e for e in entries if e.name == name]
        if not entries:
            typer.secho(
                f"error: agent '{name}' not found in manifest",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

    to_update = [e for e in entries if agent_status(e, dest) != "up-to-date"]
    if not to_update:
        typer.secho("All agents are up-to-date.", fg=typer.colors.GREEN)
        return

    breaking = []
    for entry in to_update:
        loc = local_version(entry, dest)
        if loc in ("(none)", "--"):
            continue
        try:
            local_major = int(loc.split(".")[0])
            remote_major = int(entry.version.split(".")[0])
            if remote_major > local_major:
                breaking.append(entry.name)
        except (ValueError, IndexError):
            pass

    if breaking and not yes:
        typer.secho(
            f"WARNING: BREAKING major version change in: {', '.join(breaking)}",
            fg=typer.colors.YELLOW,
        )
        if not typer.confirm("Proceed with update?", default=False):
            typer.echo("Update cancelled.")
            raise typer.Exit(code=0)

    for entry in to_update:
        try:
            pull_agent(entry, dest)
            typer.secho(f"  updated {entry.name}", fg=typer.colors.GREEN)
        except RuntimeError as exc:
            typer.secho(f"  warning: {entry.name}: {exc}", fg=typer.colors.YELLOW, err=True)


__all__ = ["agents_app"]
