"""Lifecycle commands: ``omk start``, ``omk stop``, ``omk status``.

These commands manage the Qdrant Docker container and display system state.
Docker is imported lazily so ``omk --help`` works without Docker installed.
"""

from __future__ import annotations

import importlib.metadata

import typer

from oh_my_harness.kb.cli.config import load_config, load_omk_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_container() -> QdrantContainer:  # type: ignore[name-defined]  # noqa: F821
    """Build a :class:`QdrantContainer` from the current config."""
    from oh_my_harness.kb.infra.docker_qdrant import QdrantContainer

    cfg = load_omk_config()
    return QdrantContainer(
        name=cfg.qdrant.container_name,
        image="qdrant/qdrant:latest",
        port=cfg.qdrant.port,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def start_cmd() -> None:
    """Start the Qdrant Docker container (idempotent)."""
    from oh_my_harness.kb.infra.docker_qdrant import ContainerAction, DockerNotRunningError

    try:
        container = _get_container()
        action = container.ensure_running()
    except DockerNotRunningError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    cfg = load_omk_config()
    if action == ContainerAction.ALREADY_RUNNING:
        typer.secho(
            f"Qdrant already running on :{cfg.qdrant.port}",
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(
            f"Started {cfg.qdrant.container_name} on :{cfg.qdrant.port}",
            fg=typer.colors.GREEN,
            bold=True,
        )


def stop_cmd() -> None:
    """Stop the Qdrant Docker container."""
    from oh_my_harness.kb.infra.docker_qdrant import DockerNotRunningError

    try:
        container = _get_container()
        stopped = container.stop()
    except DockerNotRunningError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    cfg = load_omk_config()
    if stopped:
        typer.secho(
            f"Stopped {cfg.qdrant.container_name}.",
            fg=typer.colors.GREEN,
            bold=True,
        )
    else:
        typer.echo(f"{cfg.qdrant.container_name} is not running.")


def status_cmd() -> None:
    """Show the current state of the oh-my-harness system."""
    from rich.console import Console
    from rich.table import Table

    from oh_my_harness.kb.cli.config import omk_config_path

    omk_cfg = load_omk_config()
    cli_cfg = load_config()

    # Try to get container status (Docker may not be running)
    container_status = "unknown"
    image_status = omk_cfg.qdrant.container_name
    try:
        from oh_my_harness.kb.infra.docker_qdrant import QdrantContainer

        qc = QdrantContainer(
            name=omk_cfg.qdrant.container_name,
            image="qdrant/qdrant:latest",
            port=omk_cfg.qdrant.port,
        )
        st = qc.status()
        container_status = "running" if st.running else "stopped"
        if st.container_id:
            image_status = f"{omk_cfg.qdrant.container_name} ({st.container_id})"
    except Exception:
        container_status = "error (Docker not running?)"

    try:
        version = importlib.metadata.version("oh-my-harness")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0 (dev)"

    table = Table(title="oh-my-harness status", show_header=False, box=None, pad_edge=True)
    table.add_column("Key", style="bold cyan", min_width=16)
    table.add_column("Value")

    table.add_row("Container", image_status)
    table.add_row("Status", container_status)
    table.add_row("Port", str(omk_cfg.qdrant.port))
    table.add_row("Knowledge base", cli_cfg.active or "(none)")
    table.add_row("Notes dir", str(omk_cfg.core.notes_root))
    table.add_row("Config file", str(omk_config_path()))
    table.add_row("Version", version)

    console = Console()
    console.print(table)
