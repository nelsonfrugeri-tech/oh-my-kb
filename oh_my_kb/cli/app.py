"""``omk`` command-line entry point (typer)."""

from __future__ import annotations

from pathlib import Path

import typer

from oh_my_kb.cli.config import (
    UniverseAlreadyExistsError,
    UniverseNotFoundError,
    add_universe,
    load_config,
    save_config,
    set_active,
)
from oh_my_kb.cli.installer import (
    Installer,
    QdrantUnreachableError,
)
from oh_my_kb.cli.paths import default_notes_root_for
from oh_my_kb.services import collection_name_for
from oh_my_kb.storage import QdrantStore, get_qdrant_url

app = typer.Typer(
    name="omk",
    help=(
        "o-kb-client — install, manage universes, expose help. "
        "Knowledge interaction stays in MCP."
    ),
    no_args_is_help=True,
)
universe_app = typer.Typer(
    help="Create, list and switch between universes.",
    no_args_is_help=True,
)
app.add_typer(universe_app, name="universe")


@app.command("help")
def help_cmd(ctx: typer.Context) -> None:
    """Show available commands with a one-line description each."""
    typer.echo(ctx.parent.get_help() if ctx.parent else ctx.get_help())


@app.command("install")
def install_cmd() -> None:
    """Bring up Qdrant, ensure the bge-m3 model, create the default universe."""
    try:
        report = Installer().run()
    except QdrantUnreachableError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho("✓ oh-my-kb is ready.", fg=typer.colors.GREEN, bold=True)
    typer.echo("")
    typer.echo("Provisioned:")
    typer.echo(f"  qdrant     : {report.qdrant_url}")
    typer.echo(f"  universe   : {report.universe} (active)")
    typer.echo(f"  notes dir  : {report.notes_root}")
    typer.echo(f"  collection : {report.collection}")
    typer.echo(f"  config     : {report.config_file}")
    typer.echo("")
    typer.echo("Steps:")
    for action in report.actions:
        typer.echo(f"  - {action}")
    typer.echo("")
    typer.echo("Next: write notes via the MCP tool (kb_write) into the active universe.")


@universe_app.command("create")
def universe_create_cmd(
    name: str = typer.Argument(..., help="Name of the new universe."),
    notes_root: str | None = typer.Option(
        None,
        "--notes-root",
        help="Override the default notes directory (defaults to ~/oh-my-kb/<name>/).",
    ),
) -> None:
    """Create a universe: directory + Qdrant collection + entry in the config."""
    target = (
        default_notes_root_for(name)
        if notes_root is None
        else Path(notes_root).expanduser()
    )
    try:
        cfg = add_universe(load_config(), name=name, notes_root=target)
    except UniverseAlreadyExistsError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    target.mkdir(parents=True, exist_ok=True)
    store = QdrantStore(get_qdrant_url())
    store.ensure_collection(collection_name_for(name))
    save_config(cfg)

    typer.secho(f"✓ universe '{name}' created.", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  notes dir  : {target}")
    typer.echo(f"  collection : {collection_name_for(name)}")


@universe_app.command("list")
def universe_list_cmd() -> None:
    """List configured universes; the active one is marked with ``*``."""
    cfg = load_config()
    if not cfg.universes:
        typer.echo("no universes configured yet. Run `omk install` first.")
        raise typer.Exit(code=0)
    for u in cfg.universes:
        marker = "*" if u.name == cfg.active else " "
        typer.echo(f" {marker} {u.name:20s} {u.collection:24s} {u.notes_root}")


@universe_app.command("use")
def universe_use_cmd(
    name: str = typer.Argument(..., help="Name of the universe to activate."),
) -> None:
    """Set ``name`` as the active universe."""
    try:
        cfg = set_active(load_config(), name)
    except UniverseNotFoundError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    save_config(cfg)
    typer.secho(f"✓ active universe is now '{name}'.", fg=typer.colors.GREEN, bold=True)


@app.command("bootstrap")
def bootstrap_cmd(
    harness: str = typer.Option(
        ...,
        "--harness",
        "-H",
        help="Target harness: claude-code | claude-desktop.",
    ),
    project_path: Path = typer.Option(  # noqa: B008
        None,
        "--project-path",
        "-p",
        help="Project root where the rules file lives. Defaults to current directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
) -> None:
    """Inject the kb-mcp rules block into the harness's rules file (idempotent)."""
    from oh_my_kb.agents import NoActiveUniverseError, bootstrap
    from oh_my_kb.agents.harness import UnknownHarnessError
    from oh_my_kb.agents.injector import MalformedBlockError

    resolved_path = project_path if project_path is not None else Path.cwd()

    cfg = load_config()
    try:
        report = bootstrap(
            harness=harness.lower(),
            project_path=resolved_path,
            active_universe=cfg.active,
        )
    except (
        UnknownHarnessError,
        NoActiveUniverseError,
        MalformedBlockError,
        FileNotFoundError,
    ) as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    action_label = {
        "created": "created",
        "inserted": "inserted",
        "replaced": "updated",
        "unchanged": "already up to date",
    }.get(report.action, report.action)

    typer.secho(
        f"✓ kb-mcp rules {action_label} for '{report.harness}'.",
        fg=typer.colors.GREEN,
        bold=True,
    )
    typer.echo(f"  universe   : {report.universe}")
    typer.echo(f"  target     : {report.target_file}")
    typer.echo(f"  action     : {report.action}")
    typer.echo(f"  bytes      : {report.bytes_written}")


@app.command("reindex")
def reindex_cmd(
    universe_name: str | None = typer.Option(
        None,
        "--universe",
        "-u",
        help="Universe to reindex. Defaults to the active universe.",
    ),
) -> None:
    """Reconcile the Qdrant collection with markdown files on disk.

    Scans the universe's notes directory, upserts every .md found (refreshing
    embeddings and correcting paths), and removes Qdrant points whose file no
    longer exists on disk.  Safe to run multiple times — fully idempotent.
    """
    from oh_my_kb.cli.reindex import NoActiveUniverseError, ReindexRunner

    try:
        runner = ReindexRunner()
        report = runner.run(universe_name)
    except NoActiveUniverseError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except UniverseNotFoundError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho(
        f"scanned {report.scanned} files, upserted {report.upserted} points, "
        f"removed {report.removed} orphans",
        fg=typer.colors.GREEN,
        bold=True,
    )


if __name__ == "__main__":  # pragma: no cover
    app()
