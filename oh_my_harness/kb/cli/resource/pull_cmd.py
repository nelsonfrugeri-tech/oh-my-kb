"""``omk resource pull`` — download resources to ``~/.claude/``."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

import typer

from oh_my_harness.kb.cli.resource.manifest import (
    Manifest,
    ResourceRecord,
    load_manifest,
    save_manifest,
)
from oh_my_harness.kb.cli.resource.registry import RESOURCE_REGISTRY, ResourceMeta
from oh_my_harness.kb.i18n import DEFAULT_LOCALE

_PLACEHOLDER_RE = re.compile(r"<!--\s*placeholder:\s*content not yet translated")
_VERSION_RE = re.compile(r"content_version:\s*(\S+)")


def _now_utc() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_content_version(content: str) -> str:
    """Extract the raw ``content_version`` string from the first HTML comment.

    Returns an empty string when the comment is absent.
    """
    first_line = content.split("\n", 1)[0]
    m = _VERSION_RE.search(first_line)
    return m.group(1) if m else ""


def _sha256_of(content: str) -> str:
    """Return the hex SHA-256 digest of *content* encoded as UTF-8."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _find_resource(name: str) -> ResourceMeta | None:
    """Look up a resource by ``short_id`` in the registry."""
    for meta in RESOURCE_REGISTRY:
        if meta.short_id == name:
            return meta
    return None


def _pull_single(
    meta: ResourceMeta,
    locale: str,
    stdout: bool,
    home: Path | None = None,
) -> tuple[bool, str]:
    """Pull one resource.

    Returns ``(success, message)`` so the ``--all`` caller can continue on
    failure and collect a per-resource summary.

    When ``stdout`` is True the content is printed and the file + manifest are
    NOT written.

    Raises ``SystemExit(1)`` directly only in single-resource (non-``--all``)
    mode; when called from ``--all`` it returns ``(False, error_message)``
    instead.
    """
    from oh_my_harness.kb.mcp.resources import read_scribe_resource

    # ── Binary guard ──────────────────────────────────────────────────────────
    if not meta.mime_type.startswith("text/"):
        msg = f"error: resource '{meta.short_id}' is binary ({meta.mime_type}); --stdout refused"
        if stdout:
            typer.secho(msg, fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        return False, msg

    # ── Fetch content ─────────────────────────────────────────────────────────
    try:
        content = read_scribe_resource(meta.uri, locale)
    except FileNotFoundError as exc:
        msg = f"error: locale '{locale}' not found for '{meta.short_id}': {exc}"
        return False, msg

    # ── Placeholder guard ─────────────────────────────────────────────────────
    if _PLACEHOLDER_RE.search(content):
        msg = (
            f"warning: '{meta.short_id}' for locale '{locale}' is a placeholder "
            "— skipping write"
        )
        typer.secho(msg, fg=typer.colors.YELLOW, err=True)
        return False, msg

    # ── --stdout path ─────────────────────────────────────────────────────────
    if stdout:
        typer.echo(content, nl=False)
        return True, "stdout"

    # ── Determine local path ──────────────────────────────────────────────────
    dest = Path(meta.local_path).expanduser()
    if home is not None:
        # Test injection: replace the tilde-expansion base with tmp_path
        rel = Path(meta.local_path.replace("~/", ""))
        dest = home / rel

    action = "updated" if dest.exists() else "created"

    # ── Write file ────────────────────────────────────────────────────────────
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")

    size_kb = dest.stat().st_size / 1024

    typer.secho(
        f"  {meta.short_id:<20s}  →  {meta.local_path}  "
        f"({size_kb:.1f} KB, action: {action})",
        fg=typer.colors.GREEN,
    )
    return True, action


def pull_cmd(
    name: str | None = typer.Argument(None, help="Short resource name (e.g. 'skills/scribe')."),
    all_: bool = typer.Option(False, "--all", help="Pull every resource in the registry."),
    stdout: bool = typer.Option(
        False, "--stdout", help="Print to stdout; do not write file or update manifest."
    ),
    locale: str = typer.Option(
        DEFAULT_LOCALE, "--locale", "-l", help="Locale for the resource content."
    ),
) -> None:
    """Download one or all resources from the MCP server to ``~/.claude/``.

    MCP server availability is not required; resources are resolved directly
    from the installed package.
    """
    # ── Mutual-exclusion check ────────────────────────────────────────────────
    if name is None and not all_:
        typer.secho(
            "error: provide a resource name or --all",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    # ── --all wins when both name and --all are given ─────────────────────────
    if all_:
        _pull_all(locale=locale, stdout=stdout)
        return

    # ── Single resource ───────────────────────────────────────────────────────
    assert name is not None
    meta = _find_resource(name)
    if meta is None:
        typer.secho(
            f"error: unknown resource '{name}'. "
            f"Available: {', '.join(m.short_id for m in RESOURCE_REGISTRY)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    # Binary + stdout check must happen before the try below
    if not meta.mime_type.startswith("text/") and stdout:
        typer.secho(
            f"error: resource '{meta.short_id}' is binary ({meta.mime_type}); --stdout refused",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    ok, result = _pull_single(meta, locale=locale, stdout=stdout)
    if not ok:
        if not result.startswith("warning:"):
            typer.secho(result, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if not stdout:
        _update_manifest(meta, locale)


def _pull_all(locale: str, stdout: bool) -> None:
    """Pull every resource in the registry sequentially."""
    typer.echo("")
    results: list[tuple[ResourceMeta, bool, str]] = []
    for meta in RESOURCE_REGISTRY:
        ok, msg = _pull_single(meta, locale=locale, stdout=stdout)
        results.append((meta, ok, msg))

    if stdout:
        return

    # ── Single manifest write at the end (avoids write-race) ─────────────────
    successful = [(meta, msg) for meta, ok, msg in results if ok]
    failed = [(meta, msg) for meta, ok, msg in results if not ok]

    if successful:
        _update_manifest_bulk(successful, locale)

    typer.echo("")
    typer.echo(f"  {len(successful)} resource(s) baixado(s) para ~/.claude/")
    if failed:
        typer.echo("")
        for meta, msg in failed:
            typer.secho(f"  FAILED {meta.short_id}: {msg}", fg=typer.colors.RED, err=True)
        typer.echo("")
        raise typer.Exit(code=1)
    typer.echo("")


def _update_manifest(
    meta: ResourceMeta,
    locale: str,
    home: Path | None = None,
) -> None:
    """Write or update the manifest entry for one resource."""
    from oh_my_harness.kb.mcp.resources import read_scribe_resource

    content = read_scribe_resource(meta.uri, locale)
    now = _now_utc()
    record = ResourceRecord(
        uri=meta.uri,
        local_path=meta.local_path,
        content_version=_extract_content_version(content),
        pulled_at=now,
        sha256=_sha256_of(content),
    )

    manifest = load_manifest(home) or Manifest(pulled_at=now, resources={})
    manifest.resources[meta.short_id] = record
    manifest.pulled_at = now
    save_manifest(manifest, home)


def _update_manifest_bulk(
    items: list[tuple[ResourceMeta, str]],
    locale: str,
    home: Path | None = None,
) -> None:
    """Update the manifest for multiple resources in a single write."""
    from oh_my_harness.kb.mcp.resources import read_scribe_resource

    now = _now_utc()
    manifest = load_manifest(home) or Manifest(pulled_at=now, resources={})

    for meta, _action in items:
        try:
            content = read_scribe_resource(meta.uri, locale)
        except FileNotFoundError:
            continue  # already reported as failed
        record = ResourceRecord(
            uri=meta.uri,
            local_path=meta.local_path,
            content_version=_extract_content_version(content),
            pulled_at=now,
            sha256=_sha256_of(content),
        )
        manifest.resources[meta.short_id] = record

    manifest.pulled_at = now
    save_manifest(manifest, home)
