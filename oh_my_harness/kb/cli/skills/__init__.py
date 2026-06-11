"""``omh skills`` — manage skills from the remote manifest."""

from __future__ import annotations

from typing import Annotated

import typer

from oh_my_harness.kb.cli._remote import load_remote_manifest
from oh_my_harness.kb.cli.skills._ops import (
    local_version,
    pull_skill,
    skill_status,
    skills_dest_root,
)

skills_app = typer.Typer(
    help="Manage skills from the official manifest.",
    no_args_is_help=True,
)


@skills_app.command("list")
def list_cmd() -> None:
    """List skills with local and remote version and status."""
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = skills_dest_root()
    header = f"{'SKILL':<22}  {'LOCAL':<10}  {'REMOTE':<10}  STATUS"
    typer.echo(header)
    typer.echo("-" * len(header))
    for entry in manifest.skills:
        loc = local_version(entry, dest)
        status = skill_status(entry, dest)
        typer.echo(f"{entry.name:<22}  {loc:<10}  {entry.version:<10}  {status}")


@skills_app.command("pull")
def pull_cmd(
    name: Annotated[str | None, typer.Argument(help="Skill name to pull.")] = None,
    all_skills: Annotated[bool, typer.Option("--all", help="Pull all skills.")] = False,
) -> None:
    """Download skill(s) to ~/.claude/skills/."""
    if not name and not all_skills:
        typer.secho("provide a skill name or --all", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = skills_dest_root()

    if all_skills:
        for entry in manifest.skills:
            try:
                n = pull_skill(entry, dest)
                typer.secho(f"  pulled {entry.name} ({n} files)", fg=typer.colors.GREEN)
            except RuntimeError as exc:
                typer.secho(f"  warning: {entry.name}: {exc}", fg=typer.colors.YELLOW, err=True)
        return

    entry_map = {e.name: e for e in manifest.skills}
    if name not in entry_map:
        typer.secho(f"error: skill '{name}' not found in manifest", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        n = pull_skill(entry_map[name], dest)
        typer.secho(f"  pulled {name} ({n} files)", fg=typer.colors.GREEN)
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@skills_app.command("diff")
def diff_cmd(
    name: Annotated[str | None, typer.Argument(help="Skill name to diff.")] = None,
) -> None:
    """Compare local sha256 vs remote for skill(s)."""
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = skills_dest_root()
    entries = manifest.skills
    if name:
        entries = [e for e in entries if e.name == name]
        if not entries:
            typer.secho(
                f"error: skill '{name}' not found in manifest",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

    header = f"{'SKILL':<22}  {'LOCAL':<10}  {'REMOTE':<10}  STATUS"
    typer.echo(header)
    typer.echo("-" * len(header))
    for entry in entries:
        loc = local_version(entry, dest)
        status = skill_status(entry, dest)
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


@skills_app.command("update")
def update_cmd(
    name: Annotated[str | None, typer.Argument(help="Skill name to update.")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Update skill(s) that are not up-to-date."""
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    dest = skills_dest_root()
    entries = manifest.skills
    if name:
        entries = [e for e in entries if e.name == name]
        if not entries:
            typer.secho(
                f"error: skill '{name}' not found in manifest",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

    to_update = [e for e in entries if skill_status(e, dest) != "up-to-date"]
    if not to_update:
        typer.secho("All skills are up-to-date.", fg=typer.colors.GREEN)
        return

    # Check for BREAKING changes
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
            n = pull_skill(entry, dest)
            typer.secho(f"  updated {entry.name} ({n} files)", fg=typer.colors.GREEN)
        except RuntimeError as exc:
            typer.secho(f"  warning: {entry.name}: {exc}", fg=typer.colors.YELLOW, err=True)


__all__ = ["skills_app"]
