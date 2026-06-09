"""Pure business logic for oh-my-kb resource management.

This module contains no Typer, no Rich, no CLI concerns — only pure Python
data structures and functions that both CLI and MCP handlers can call.

CLI commands call these functions and format results with Typer/Rich.
MCP handlers call these functions and format results as plain text for the LLM.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from oh_my_kb.cli.manifest import (
    Manifest,
    ManifestEntry,
    save_manifest,
    upsert_entry,
)
from oh_my_kb.mcp.resources import (
    _URI_TO_RESOURCE_ID,
    compute_sha256,
    parse_content_version,
    read_scribe_resource,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Forward mapping: resource_id → URI
_ID_TO_URI: dict[str, str] = {v: k for k, v in _URI_TO_RESOURCE_ID.items()}

# resource_id → local_path with ~ (not expanded)
_ID_TO_LOCAL_PATH: dict[str, str] = {
    "skills/scribe": "~/.claude/skills/scribe/SKILL.md",
    "skills/scribe-template": "~/.claude/skills/scribe/template.md",
}


def _extract_content_version(content: str) -> str:
    """Extract ``content_version`` from the HTML comment frontmatter."""
    return parse_content_version(content)


def _sha256_of(content: str) -> str:
    """Return the hex SHA-256 digest of *content* encoded as UTF-8."""
    return compute_sha256(content)


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _local_path_for(resource_id: str, home: Path | None = None) -> Path:
    """Return the expanded local path for *resource_id*, respecting test injection."""
    local_path_str = _ID_TO_LOCAL_PATH.get(resource_id, f"~/.claude/{resource_id}")
    if home is not None:
        rel = Path(local_path_str.replace("~/", ""))
        return home / rel
    return Path(local_path_str).expanduser()


def _all_resource_ids() -> list[str]:
    """Return all known resource IDs in a stable order."""
    return list(_ID_TO_URI.keys())


# ---------------------------------------------------------------------------
# Dataclasses for structured results
# ---------------------------------------------------------------------------


@dataclass
class ResourceStatus:
    """Status of one resource — used by list_resources_with_status."""

    resource_id: str
    server_version: str
    local_version: str | None  # None when not installed
    is_outdated: bool
    is_installed: bool


@dataclass
class ResourceDiffEntry:
    """Diff result for a single resource."""

    resource_id: str
    server_version: str
    local_version: str | None
    is_changed: bool
    diff_text: str  # unified diff text; empty when unchanged


@dataclass
class DiffResult:
    """Result of compute_diff — a list of per-resource diffs."""

    entries: list[ResourceDiffEntry] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        return sum(1 for e in self.entries if e.is_changed)

    @property
    def unchanged_count(self) -> int:
        return sum(1 for e in self.entries if not e.is_changed)


@dataclass
class ResourceUpdateEntry:
    """Result for a single resource after apply_update."""

    resource_id: str
    old_version: str | None
    new_version: str
    local_path: str
    was_updated: bool


@dataclass
class UpdateResult:
    """Result of apply_update."""

    entries: list[ResourceUpdateEntry] = field(default_factory=list)
    claude_md_regenerated: bool = False
    claude_md_error: str | None = None

    @property
    def updated_count(self) -> int:
        return sum(1 for e in self.entries if e.was_updated)

    @property
    def unchanged_count(self) -> int:
        return sum(1 for e in self.entries if not e.was_updated)


# ---------------------------------------------------------------------------
# Public API — called by both CLI and MCP handlers
# ---------------------------------------------------------------------------


def list_resources_with_status(manifest: Manifest | None) -> list[ResourceStatus]:
    """Return status for every registry resource compared with the local manifest.

    When *manifest* is ``None`` every resource is treated as not installed.
    """
    statuses: list[ResourceStatus] = []
    for resource_id in _all_resource_ids():
        uri = _ID_TO_URI[resource_id]
        content = read_scribe_resource(uri)
        server_version = _extract_content_version(content)
        server_sha = _sha256_of(content)

        if manifest is None:
            statuses.append(
                ResourceStatus(
                    resource_id=resource_id,
                    server_version=server_version,
                    local_version=None,
                    is_outdated=False,
                    is_installed=False,
                )
            )
        else:
            record: ManifestEntry | None = manifest.resources.get(resource_id)
            if record is None:
                statuses.append(
                    ResourceStatus(
                        resource_id=resource_id,
                        server_version=server_version,
                        local_version=None,
                        is_outdated=True,
                        is_installed=False,
                    )
                )
            else:
                is_outdated = record.sha256 != server_sha
                statuses.append(
                    ResourceStatus(
                        resource_id=resource_id,
                        server_version=server_version,
                        local_version=record.content_version or None,
                        is_outdated=is_outdated,
                        is_installed=True,
                    )
                )
    return statuses


def compute_diff(
    manifest: Manifest,
    resource_id: str | None,
) -> DiffResult:
    """Compute unified diffs between local files and server versions.

    Args:
        manifest: The loaded local manifest.
        resource_id: If given, diff only that resource; otherwise diff all.

    Raises:
        KeyError: If *resource_id* is not found in the resource registry.
    """
    if resource_id is not None:
        if resource_id not in _ID_TO_URI:
            raise KeyError(resource_id)
        targets = [resource_id]
    else:
        targets = _all_resource_ids()

    entries: list[ResourceDiffEntry] = []
    for rid in targets:
        uri = _ID_TO_URI[rid]
        server_text = read_scribe_resource(uri)
        server_sha = _sha256_of(server_text)
        server_version = _extract_content_version(server_text)

        record = manifest.resources.get(rid)
        if record is None:
            local_version: str | None = None
            is_changed = True
        elif record.sha256 == server_sha:
            local_version = record.content_version or None
            is_changed = False
        else:
            local_version = record.content_version or None
            is_changed = True

        if is_changed:
            local_path = Path(_ID_TO_LOCAL_PATH.get(rid, f"~/.claude/{rid}")).expanduser()
            local_text = local_path.read_text(encoding="utf-8") if local_path.exists() else ""
            diff_lines = list(
                difflib.unified_diff(
                    local_text.splitlines(keepends=True),
                    server_text.splitlines(keepends=True),
                    fromfile=f"local/{rid}",
                    tofile=f"server/{rid}",
                    lineterm="",
                )
            )
            diff_text = "\n".join(diff_lines)
        else:
            diff_text = ""

        entries.append(
            ResourceDiffEntry(
                resource_id=rid,
                server_version=server_version,
                local_version=local_version,
                is_changed=is_changed,
                diff_text=diff_text,
            )
        )

    return DiffResult(entries=entries)


def apply_update(
    manifest: Manifest,
    resource_id: str | None,
    home: Path | None = None,
) -> UpdateResult:
    """Apply pending updates from the server to disk and update the manifest.

    Writes changed resources to ``~/.claude/``, updates *manifest* in-memory,
    and persists it.  Does NOT regenerate CLAUDE.md — callers are responsible
    for calling ``do_bootstrap`` themselves (or catching the error).

    Args:
        manifest: The loaded local manifest (mutated in-place and saved).
        resource_id: If given, update only that resource; otherwise update all.
        home: Override for Path.home() — used in tests.

    Raises:
        KeyError: If *resource_id* is not found in the resource registry.
        PermissionError: If a resource file cannot be written.
    """
    if resource_id is not None:
        if resource_id not in _ID_TO_URI:
            raise KeyError(resource_id)
        targets = [resource_id]
    else:
        targets = _all_resource_ids()

    entries: list[ResourceUpdateEntry] = []
    any_updated = False

    for rid in targets:
        uri = _ID_TO_URI[rid]
        content = read_scribe_resource(uri)
        server_sha = _sha256_of(content)
        server_version = _extract_content_version(content)
        local_path_str = _ID_TO_LOCAL_PATH.get(rid, f"~/.claude/{rid}")

        record = manifest.resources.get(rid)
        old_version = record.content_version if record else None

        if record is not None and record.sha256 == server_sha:
            # No change
            entries.append(
                ResourceUpdateEntry(
                    resource_id=rid,
                    old_version=old_version,
                    new_version=server_version,
                    local_path=local_path_str,
                    was_updated=False,
                )
            )
            continue

        # Needs update — write to disk
        dest = _local_path_for(rid, home=home)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

        upsert_entry(
            manifest=manifest,
            resource_id=rid,
            uri=uri,
            local_path=local_path_str,
            content_version=server_version,
            sha256=server_sha,
        )
        any_updated = True
        entries.append(
            ResourceUpdateEntry(
                resource_id=rid,
                old_version=old_version,
                new_version=server_version,
                local_path=local_path_str,
                was_updated=True,
            )
        )

    if any_updated:
        save_manifest(manifest, home=home)

    return UpdateResult(entries=entries)
