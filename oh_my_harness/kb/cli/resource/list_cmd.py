"""``omk resource list`` — display available resources with their destinations."""

from __future__ import annotations

import typer

from oh_my_harness.kb.cli.resource.registry import RESOURCE_REGISTRY


def list_cmd() -> None:
    """List all available MCP resources with their URI and local destination."""
    typer.echo("")
    typer.echo("  Resources disponíveis (universe: default)")
    typer.echo("")

    for meta in RESOURCE_REGISTRY:
        typer.echo(f"  {meta.short_id:<20s}  {meta.uri:<40s}  → {meta.local_path}")

    typer.echo("")
    typer.echo(f"  {len(RESOURCE_REGISTRY)} resource(s) encontrado(s).")
    typer.echo("")
