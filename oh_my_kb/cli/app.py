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


# ---------------------------------------------------------------------------
# omk install — interactive wizard
# ---------------------------------------------------------------------------


@app.command("install")
def install_cmd(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Accept all defaults and run non-interactively (for CI/scripts).",
    ),
) -> None:
    """Interactive wizard: configure, start Qdrant, create universe, bootstrap harness."""
    import sys

    from oh_my_kb.cli.config import (
        OmkConfig,
        OmkCoreConfig,
        OmkHarnessConfig,
        OmkQdrantConfig,
        save_omk_config,
    )
    from oh_my_kb.cli.install.wizard import Wizard

    # ── Wizard ──
    wizard = Wizard(non_interactive=yes)
    choices = wizard.run()

    typer.echo(choices.summary())

    # Confirmation — skipped when --yes
    if not yes:
        if not sys.stdin.isatty():
            typer.secho(
                "error: non-TTY stdin detected and --yes not given; "
                "re-run with --yes to proceed non-interactively.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        if not choices.confirm():
            typer.echo("Instalacao cancelada.")
            raise typer.Exit(code=0)

    typer.echo("")
    typer.echo("  Instalando Oh My KB...")
    typer.echo("")

    # ── [1/6] Docker check ──
    typer.echo("  [1/6] Verificando Docker...")
    from oh_my_kb.infra.docker_qdrant import DockerNotRunningError, QdrantContainer
    try:
        qc = QdrantContainer(
            name="oh-my-kb-qdrant",
            image="qdrant/qdrant:latest",
            port=choices.qdrant_port,
        )
        qc.status()
    except DockerNotRunningError as exc:
        typer.secho(f"  error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho("  [1/6] Docker OK", fg=typer.colors.GREEN)

    # ── [2/6] Ensure Qdrant container ──
    typer.echo("  [2/6] Iniciando Qdrant (qdrant/qdrant:latest) ...")
    try:
        qc.ensure_image()
        action = qc.ensure_running()
    except DockerNotRunningError as exc:
        typer.secho(f"  error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.secho(f"  error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(
        f"  [2/6] Qdrant {action} na porta {choices.qdrant_port}",
        fg=typer.colors.GREEN,
    )

    # ── [3/6] Create universe directory ──
    typer.echo(f"  [3/6] Criando universe '{choices.universe}' ...")
    universe_dir = choices.notes_root / choices.universe
    universe_dir.mkdir(parents=True, exist_ok=True)
    typer.secho(f"  [3/6] {universe_dir}/", fg=typer.colors.GREEN)

    # ── [4/6] Persist configuration ──
    typer.echo("  [4/6] Salvando configuracao ...")
    from oh_my_kb.cli.config import config_path

    omk_cfg = OmkConfig(
        core=OmkCoreConfig(
            notes_root=choices.notes_root,
            default_universe=choices.universe,
            models_cache=choices.models_cache,
        ),
        qdrant=OmkQdrantConfig(
            port=choices.qdrant_port,
            container_name="oh-my-kb-qdrant",
        ),
        harness=OmkHarnessConfig(active=choices.harness),
    )
    save_omk_config(omk_cfg)

    qdrant_url = f"http://localhost:{choices.qdrant_port}"
    cli_cfg = load_config()
    if not cli_cfg.has(choices.universe):
        cli_cfg = add_universe(cli_cfg, name=choices.universe, notes_root=universe_dir)
    cli_cfg = set_active(cli_cfg, choices.universe)
    save_config(cli_cfg)

    store = QdrantStore(qdrant_url)
    coll_name = collection_name_for(choices.universe)
    if not store.collection_exists(coll_name):
        store.ensure_collection(coll_name)

    typer.secho(f"  [4/6] {config_path()}", fg=typer.colors.GREEN)

    # ── [5/6] Generate dynamic block ──
    typer.echo("  [5/6] Gerando bloco de regras ...")
    from oh_my_kb.agents.template import render_dynamic_block
    render_dynamic_block(choices.universe)
    typer.secho("  [5/6] Bloco gerado com sucesso", fg=typer.colors.GREEN)

    # ── [6/6] Bootstrap harness ──
    typer.echo("  [6/6] Injetando bloco em ~/.claude/CLAUDE.md ...")
    from oh_my_kb.agents.bootstrap import do_bootstrap
    report = do_bootstrap(choices.harness, choices.universe)
    typer.secho(
        f"  [6/6] Bloco omk {report.action} em {report.target_file}",
        fg=typer.colors.GREEN,
        bold=True,
    )

    typer.echo("")
    typer.secho("  Oh My KB instalado com sucesso!", fg=typer.colors.GREEN, bold=True)
    typer.echo("")
    typer.echo("  Proximos passos:")
    typer.echo("    * Abra o Claude Code em qualquer projeto — o kb-mcp ja esta ativo.")
    typer.echo("    * omk status          — verificar o estado do sistema")
    typer.echo("    * omk resource diff   — ver atualizacoes disponiveis nos resources")
    typer.echo("    * omk resource update — aplicar atualizacoes (regenera o CLAUDE.md)")
    typer.echo("")


# ---------------------------------------------------------------------------
# omk start / stop / status — lifecycle commands
# ---------------------------------------------------------------------------


@app.command("start")
def start_cmd() -> None:
    """Start the Qdrant Docker container (idempotent)."""
    from oh_my_kb.cli.lifecycle import start_cmd as _start
    _start()


@app.command("stop")
def stop_cmd() -> None:
    """Stop the Qdrant Docker container."""
    from oh_my_kb.cli.lifecycle import stop_cmd as _stop
    _stop()


@app.command("status")
def status_cmd() -> None:
    """Show the current state of the oh-my-kb system."""
    from oh_my_kb.cli.lifecycle import status_cmd as _status
    _status()


# ---------------------------------------------------------------------------
# omk universe — sub-commands
# ---------------------------------------------------------------------------


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

    typer.secho(f"universe '{name}' created.", fg=typer.colors.GREEN, bold=True)
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
    typer.secho(f"active universe is now '{name}'.", fg=typer.colors.GREEN, bold=True)


@app.command("reindex")
def reindex_cmd(
    universe_name: str | None = typer.Option(
        None,
        "--universe",
        "-u",
        help="Universe to reindex. Defaults to the active universe.",
    ),
) -> None:
    """Reconcile the Qdrant collection with markdown files on disk."""
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
