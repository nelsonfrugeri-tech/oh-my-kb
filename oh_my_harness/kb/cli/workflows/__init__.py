"""``omh workflows`` — manage workflows from the remote manifest."""

from __future__ import annotations

from typing import Annotated

import typer

from oh_my_harness.kb.cli._deps import resolve, resolve_all
from oh_my_harness.kb.cli._remote import (
    AgentEntry,
    Manifest,
    SkillEntry,
    WorkflowEntry,
    load_remote_manifest,
)
from oh_my_harness.kb.cli.agents._ops import agents_dest_root, pull_agent
from oh_my_harness.kb.cli.skills._ops import pull_skill, skills_dest_root
from oh_my_harness.kb.cli.workflows._ops import (
    local_version,
    pull_workflow,
    workflow_status,
    workflows_dest_root,
)

workflows_app = typer.Typer(
    help="Manage workflows from the official manifest.",
    no_args_is_help=True,
)


@workflows_app.command("list")
def list_cmd() -> None:
    """List installed workflows from ~/.claude/workflows/."""
    dest = workflows_dest_root()
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    header = f"{'WORKFLOW':<22}  {'LOCAL':<10}  {'REMOTE':<10}  STATUS"
    typer.echo(header)
    typer.echo("-" * len(header))
    for entry in manifest.workflows:
        loc = local_version(entry, dest)
        status = workflow_status(entry, dest)
        typer.echo(f"{entry.name:<22}  {loc:<10}  {entry.version:<10}  {status}")


def _pull_workflow_set(
    workflows: list[WorkflowEntry],
    agents: list[AgentEntry],
    skills: list[SkillEntry],
    manifest: Manifest,
    label: str,
    no_deps: bool,
) -> None:
    """Pull a resolved workflow set with all transitive deps in topo order."""
    skill_dest = skills_dest_root()
    agent_dest = agents_dest_root()
    wf_dest = workflows_dest_root()

    if no_deps:
        for entry in workflows:
            try:
                pull_workflow(entry, wf_dest)
                typer.secho(f"  pulled {entry.name}", fg=typer.colors.GREEN)
            except RuntimeError as exc:
                typer.secho(f"  warning: {entry.name}: {exc}", fg=typer.colors.YELLOW, err=True)
        return

    n_agents = len(agents)
    n_skills = len(skills)
    if n_agents or n_skills:
        typer.echo(
            f"pulling {label} ({n_agents} agents + {n_skills} skills as dependencies)"
        )

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
            typer.secho(f"  pulled agent {agent.name}  [dep]", fg=typer.colors.GREEN)
        except RuntimeError as exc:
            typer.secho(
                f"  warning: agent {agent.name}: {exc}", fg=typer.colors.YELLOW, err=True
            )

    # Finally workflows (roots)
    for wf in workflows:
        if wf.name in already_pulled:
            continue
        already_pulled.add(wf.name)
        try:
            pull_workflow(wf, wf_dest)
            typer.secho(f"  pulled {wf.name}", fg=typer.colors.GREEN)
        except RuntimeError as exc:
            typer.secho(f"  warning: {wf.name}: {exc}", fg=typer.colors.YELLOW, err=True)


@workflows_app.command("pull")
def pull_cmd(
    name: Annotated[str | None, typer.Argument(help="Workflow name to pull.")] = None,
    all_workflows: Annotated[bool, typer.Option("--all", help="Pull all workflows.")] = False,
    no_deps: Annotated[
        bool,
        typer.Option(
            "--no-deps", help="Pull only the named workflow, skip dependency resolution."
        ),
    ] = False,
) -> None:
    """Download workflow(s) to ~/.claude/workflows/.

    By default also pulls every referenced agent and each agent's skill
    dependencies (transitive closure, topological order).  Use --no-deps
    for legacy behaviour (workflow file only).
    """
    if not name and not all_workflows:
        typer.secho("provide a workflow name or --all", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if all_workflows:
        rs = resolve_all(manifest, "workflow")
        _pull_workflow_set(rs.workflows, rs.agents, rs.skills, manifest, "all workflows", no_deps)
        return

    entry_map = {e.name: e for e in manifest.workflows}
    if name not in entry_map:
        typer.secho(
            f"error: workflow '{name}' not found in manifest", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    rs = resolve(manifest, "workflow", name)
    _pull_workflow_set(rs.workflows, rs.agents, rs.skills, manifest, name, no_deps)


@workflows_app.command("diff")
def diff_cmd(
    name: Annotated[str | None, typer.Argument(help="Workflow name to diff.")] = None,
) -> None:
    """Compare local sha256 vs remote for workflow(s)."""
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = workflows_dest_root()
    entries = manifest.workflows
    if name:
        entries = [e for e in entries if e.name == name]
        if not entries:
            typer.secho(
                f"error: workflow '{name}' not found in manifest",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

    header = f"{'WORKFLOW':<22}  {'LOCAL':<10}  {'REMOTE':<10}  STATUS"
    typer.echo(header)
    typer.echo("-" * len(header))
    for entry in entries:
        loc = local_version(entry, dest)
        status = workflow_status(entry, dest)
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


@workflows_app.command("update")
def update_cmd(
    name: Annotated[str | None, typer.Argument(help="Workflow name to update.")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
    no_deps: Annotated[
        bool,
        typer.Option(
            "--no-deps", help="Update only the named workflow, skip dependency resolution."
        ),
    ] = False,
) -> None:
    """Update workflow(s) that are not up-to-date.

    By default also updates every referenced agent and their skill
    dependencies.  Use --no-deps for legacy behaviour.
    """
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = workflows_dest_root()
    entries = manifest.workflows
    if name:
        entries = [e for e in entries if e.name == name]
        if not entries:
            typer.secho(
                f"error: workflow '{name}' not found in manifest",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

    to_update = [e for e in entries if workflow_status(e, dest) != "up-to-date"]
    if not to_update:
        typer.secho("All workflows are up-to-date.", fg=typer.colors.GREEN)
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
            pull_workflow(entry, dest)
            typer.secho(f"  updated {entry.name}", fg=typer.colors.GREEN)
        except RuntimeError as exc:
            typer.secho(f"  warning: {entry.name}: {exc}", fg=typer.colors.YELLOW, err=True)


__all__ = ["workflows_app"]
