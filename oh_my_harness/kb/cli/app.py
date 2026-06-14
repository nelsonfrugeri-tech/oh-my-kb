"""``omh`` command-line entry point (typer)."""

from __future__ import annotations

from pathlib import Path

import typer

from oh_my_harness import __version__ as _OMH_VERSION
from oh_my_harness.kb.cli.agents import agents_app
from oh_my_harness.kb.cli.config import (
    KbAlreadyExistsError,
    KbNotFoundError,
    add_kb,
    load_config,
    save_config,
    set_active,
)
from oh_my_harness.kb.cli.paths import default_notes_root_for
from oh_my_harness.kb.cli.skills import skills_app
from oh_my_harness.kb.services import collection_name_for
from oh_my_harness.kb.storage import QdrantStore, get_qdrant_url

app = typer.Typer(
    name="omh",
    help=(
        "oh-my-harness — install, manage knowledge bases, expose help. "
        "Knowledge interaction stays in MCP."
    ),
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"omh {_OMH_VERSION}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show the omh CLI version and exit.",
    ),
) -> None:
    """oh-my-harness CLI (omh)."""
    return None
universe_app = typer.Typer(
    help="Create, list and switch between knowledge bases.",
    no_args_is_help=True,
)
app.add_typer(universe_app, name="kb")
app.add_typer(skills_app, name="skills")
app.add_typer(agents_app, name="agents")


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
    """Interactive wizard: configure, start Qdrant, create knowledge base, bootstrap harness."""
    import sys

    from oh_my_harness.kb.cli.config import (
        OmkConfig,
        OmkCoreConfig,
        OmkHarnessConfig,
        OmkQdrantConfig,
        save_omk_config,
    )
    from oh_my_harness.kb.cli.install.wizard import Wizard

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
    typer.echo("  Instalando Oh My Harness...")
    typer.echo("")

    # ── [1/8] Docker check ──
    typer.echo("  [1/8] Verificando Docker...")
    from oh_my_harness.kb.infra.docker_qdrant import DockerNotRunningError, QdrantContainer
    try:
        qc = QdrantContainer(
            name="oh-my-harness-qdrant",
            image="qdrant/qdrant:latest",
            port=choices.qdrant_port,
        )
        qc.status()
    except DockerNotRunningError as exc:
        typer.secho(f"  error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho("  [1/8] Docker OK", fg=typer.colors.GREEN)

    # ── [2/8] Ensure Qdrant container ──
    typer.echo("  [2/8] Iniciando Qdrant (qdrant/qdrant:latest) ...")
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
        f"  [2/8] Qdrant {action} na porta {choices.qdrant_port}",
        fg=typer.colors.GREEN,
    )

    # ── [3/8] Create knowledge base directory ──
    typer.echo(f"  [3/8] Criando knowledge base '{choices.universe}' ...")
    universe_dir = choices.notes_root / choices.universe
    universe_dir.mkdir(parents=True, exist_ok=True)
    typer.secho(f"  [3/8] {universe_dir}/", fg=typer.colors.GREEN)

    # ── [4/8] Persist configuration ──
    typer.echo("  [4/8] Salvando configuracao ...")
    from oh_my_harness.kb.cli.config import config_path

    omk_cfg = OmkConfig(
        core=OmkCoreConfig(
            notes_root=choices.notes_root,
            default_kb=choices.universe,
            models_cache=choices.models_cache,
        ),
        qdrant=OmkQdrantConfig(
            port=choices.qdrant_port,
            container_name="oh-my-harness-qdrant",
        ),
        harness=OmkHarnessConfig(active=choices.harness),
    )
    save_omk_config(omk_cfg)

    qdrant_url = f"http://localhost:{choices.qdrant_port}"
    cli_cfg = load_config()
    if not cli_cfg.has(choices.universe):
        cli_cfg = add_kb(cli_cfg, name=choices.universe, notes_root=universe_dir)
    cli_cfg = set_active(cli_cfg, choices.universe)
    save_config(cli_cfg)

    store = QdrantStore(qdrant_url)
    coll_name = collection_name_for(choices.universe)
    if not store.collection_exists(coll_name):
        store.ensure_collection(coll_name)

    typer.secho(f"  [4/8] {config_path()}", fg=typer.colors.GREEN)

    # ── [5/8] Generate dynamic block ──
    typer.echo("  [5/8] Gerando bloco de regras ...")
    from oh_my_harness.kb.agents.template import render_dynamic_block
    render_dynamic_block(choices.universe)
    typer.secho("  [5/8] Bloco gerado com sucesso", fg=typer.colors.GREEN)

    # ── [6/8] Bootstrap harness ──
    typer.echo("  [6/8] Injetando bloco em ~/.claude/CLAUDE.md ...")
    from oh_my_harness.kb.agents.bootstrap import do_bootstrap
    report = do_bootstrap(choices.harness, choices.universe)
    typer.secho(
        f"  [6/8] Bloco omh {report.action} em {report.target_file}",
        fg=typer.colors.GREEN,
        bold=True,
    )

    # ── [7/8] Write initial user preferences block ──
    typer.echo("  [7/8] Escrevendo seção 'Preferências do Usuário' ...")
    from oh_my_harness.agents.preferences.install import write_initial_preferences
    prefs_action = write_initial_preferences()
    typer.secho(
        f"  [7/8] Seção 'Preferências do Usuário' {prefs_action} em ~/.claude/CLAUDE.md",
        fg=typer.colors.GREEN,
        bold=True,
    )

    # ── [8/8] Download skills and agents (optional) ──
    if choices.download_extras:
        typer.echo("  [8/8] Baixando skills e agents...")
        from oh_my_harness.kb.cli.agents._ops import pull_all_agents
        from oh_my_harness.kb.cli.skills._ops import pull_all_skills

        skills_count, skills_errors = pull_all_skills()
        if skills_errors:
            for err in skills_errors:
                typer.secho(f"  warning: {err}", fg=typer.colors.YELLOW, err=True)

        agents_count, agents_errors = pull_all_agents()
        if agents_errors:
            for err in agents_errors:
                typer.secho(f"  warning: {err}", fg=typer.colors.YELLOW, err=True)

        if skills_errors or agents_errors:
            typer.secho(
                f"  [8/8] skills: {skills_count} baixados, agents: {agents_count} baixados"
                " (alguns falharam — rode `omh skills pull --all` depois)",
                fg=typer.colors.YELLOW,
            )
        else:
            typer.secho(
                f"  [8/8] skills: {skills_count} baixados, agents: {agents_count} baixados",
                fg=typer.colors.GREEN,
                bold=True,
            )
    else:
        typer.secho(
            "  [8/8] skills e agents pulados (rode `omh skills pull --all` "
            "e `omh agents pull --all` depois se mudar de ideia)",
            fg=typer.colors.YELLOW,
        )

    typer.echo("")
    typer.secho("  Oh My Harness instalado com sucesso!", fg=typer.colors.GREEN, bold=True)
    typer.echo("")
    typer.echo("  Proximos passos:")
    typer.echo("    * Abra o Claude Code em qualquer projeto — o kb-mcp ja esta ativo.")
    typer.echo("    * omh status          — verificar o estado do sistema")
    typer.echo("    * omh skills list     — ver skills disponíveis")
    typer.echo("    * omh agents list     — ver agents disponíveis")
    typer.echo("    * omh skills diff     — ver atualizações disponíveis nos skills")
    typer.echo("    * omh skills update   — aplicar atualizações")
    typer.echo("")


# ---------------------------------------------------------------------------
# omk start / stop / status — lifecycle commands
# ---------------------------------------------------------------------------


@app.command("start")
def start_cmd() -> None:
    """Start the Qdrant Docker container (idempotent)."""
    from oh_my_harness.kb.cli.lifecycle import start_cmd as _start
    _start()


@app.command("stop")
def stop_cmd() -> None:
    """Stop the Qdrant Docker container."""
    from oh_my_harness.kb.cli.lifecycle import stop_cmd as _stop
    _stop()


@app.command("status")
def status_cmd() -> None:
    """Show the current state of the oh-my-harness system."""
    from oh_my_harness.kb.cli.lifecycle import status_cmd as _status
    _status()


# ---------------------------------------------------------------------------
# omk kb — sub-commands
# ---------------------------------------------------------------------------


@universe_app.command("create")
def universe_create_cmd(
    name: str = typer.Argument(..., help="Name of the new knowledge base."),
    notes_root: str | None = typer.Option(
        None,
        "--notes-root",
        help="Override the default notes directory (defaults to ~/oh-my-harness/<name>/).",
    ),
) -> None:
    """Create a knowledge base: directory + Qdrant collection + entry in the config."""
    target = (
        default_notes_root_for(name)
        if notes_root is None
        else Path(notes_root).expanduser()
    )
    try:
        cfg = add_kb(load_config(), name=name, notes_root=target)
    except KbAlreadyExistsError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    target.mkdir(parents=True, exist_ok=True)
    store = QdrantStore(get_qdrant_url())
    try:
        store.ensure_collection(collection_name_for(name))
    except Exception as exc:
        typer.secho(
            f"error: could not reach Qdrant ({exc.__class__.__name__}). "
            f"Make sure Docker is running and `omh start` has been executed.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc
    save_config(cfg)

    typer.secho(f"knowledge base '{name}' created.", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  notes dir  : {target}")
    typer.echo(f"  collection : {collection_name_for(name)}")


@universe_app.command("list")
def universe_list_cmd() -> None:
    """List configured knowledge bases; the active one is marked with ``*``."""
    cfg = load_config()
    if not cfg.universes:
        typer.echo("No knowledge bases configured yet. Run `omh install` first.")
        raise typer.Exit(code=0)
    for u in cfg.universes:
        marker = "*" if u.name == cfg.active else " "
        typer.echo(f" {marker} {u.name:20s} {u.collection:24s} {u.notes_root}")


@universe_app.command("use")
def universe_use_cmd(
    name: str = typer.Argument(..., help="Name of the knowledge base to activate."),
) -> None:
    """Set ``name`` as the active knowledge base."""
    try:
        cfg = set_active(load_config(), name)
    except KbNotFoundError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    save_config(cfg)
    typer.secho(f"active knowledge base is now '{name}'.", fg=typer.colors.GREEN, bold=True)


@app.command("reindex")
def reindex_cmd(
    kb_name: str | None = typer.Option(
        None,
        "--kb",
        "--universe",
        "-u",
        help="Knowledge base to reindex. Defaults to the active knowledge base.",
    ),
) -> None:
    """Reconcile the Qdrant collection with markdown files on disk."""
    from oh_my_harness.kb.cli.reindex import NoActiveKbError, ReindexRunner

    try:
        runner = ReindexRunner()
        report = runner.run(kb_name)
    except NoActiveKbError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except KbNotFoundError as exc:
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
