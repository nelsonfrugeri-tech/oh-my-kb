"""``omh agents`` — manage agents from the remote manifest."""

from __future__ import annotations

from typing import Annotated

import typer

from oh_my_harness.kb.cli._deps import resolve, resolve_all
from oh_my_harness.kb.cli._remote import AgentEntry, Manifest, SkillEntry, load_remote_manifest
from oh_my_harness.kb.cli.agents._ops import (
    agent_status,
    agents_dest_root,
    local_version,
    pull_agent,
)
from oh_my_harness.kb.cli.skills._ops import pull_skill, skills_dest_root

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


def _pull_agent_set(
    agents: list[AgentEntry],
    skills: list[SkillEntry],
    manifest: Manifest,
    label: str,
    no_deps: bool,
) -> None:
    """Pull a resolved agent set (and their skill deps) in topological order."""
    skill_dest = skills_dest_root()
    agent_dest = agents_dest_root()

    if no_deps:
        for entry in agents:
            try:
                pull_agent(entry, agent_dest)
                typer.secho(f"  pulled {entry.name}", fg=typer.colors.GREEN)
            except RuntimeError as exc:
                typer.secho(f"  warning: {entry.name}: {exc}", fg=typer.colors.YELLOW, err=True)
        return

    n_skills = len(skills)
    n_agents = len(agents)
    if n_skills or n_agents > len(agents):
        typer.echo(f"pulling {label} ({n_agents} agents + {n_skills} skills as dependencies)")

    already_pulled: set[str] = set()
    # Skills first (leaves)
    for skill in skills:
        if skill.name in already_pulled:
            continue
        already_pulled.add(skill.name)
        try:
            n = pull_skill(skill, skill_dest)
            typer.secho(
                f"  pulled skill {skill.name} ({n} files)  [dep]", fg=typer.colors.GREEN
            )
        except RuntimeError as exc:
            typer.secho(
                f"  warning: skill {skill.name}: {exc}", fg=typer.colors.YELLOW, err=True
            )
    # Then agents
    for agent in agents:
        if agent.name in already_pulled:
            continue
        already_pulled.add(agent.name)
        try:
            pull_agent(agent, agent_dest)
            typer.secho(f"  pulled {agent.name}", fg=typer.colors.GREEN)
        except RuntimeError as exc:
            typer.secho(f"  warning: {agent.name}: {exc}", fg=typer.colors.YELLOW, err=True)


@agents_app.command("pull")
def pull_cmd(
    name: Annotated[str | None, typer.Argument(help="Agent name to pull.")] = None,
    all_agents: Annotated[bool, typer.Option("--all", help="Pull all agents.")] = False,
    no_deps: Annotated[
        bool,
        typer.Option(
            "--no-deps", help="Pull only the named agent, skip dependency resolution."
        ),
    ] = False,
) -> None:
    """Download agent(s) to ~/.claude/agents/.

    By default also pulls transitive skill dependencies declared in each
    agent's frontmatter.  Use --no-deps for legacy behaviour.
    """
    if not name and not all_agents:
        typer.secho("provide an agent name or --all", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if all_agents:
        rs = resolve_all(manifest, "agent")
        _pull_agent_set(rs.agents, rs.skills, manifest, "all agents", no_deps=no_deps)
        return

    entry_map = {e.name: e for e in manifest.agents}
    if name not in entry_map:
        typer.secho(
            f"error: agent '{name}' not found in manifest", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    rs = resolve(manifest, "agent", name)
    _pull_agent_set(rs.agents, rs.skills, manifest, name, no_deps=no_deps)


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
    no_deps: Annotated[
        bool,
        typer.Option(
            "--no-deps", help="Update only the named agent, skip dependency resolution."
        ),
    ] = False,
) -> None:
    """Update agent(s) that are not up-to-date.

    By default also updates transitive skill dependencies.  Use --no-deps
    for legacy behaviour.
    """
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

    already_updated: set[str] = set()
    for entry in to_update:
        if entry.name in already_updated:
            continue
        already_updated.add(entry.name)
        try:
            pull_agent(entry, dest)
            typer.secho(f"  updated {entry.name}", fg=typer.colors.GREEN)
        except RuntimeError as exc:
            typer.secho(f"  warning: {entry.name}: {exc}", fg=typer.colors.YELLOW, err=True)


__all__ = ["agents_app"]
