"""Shared workflow operations used by list/pull/diff/update commands."""

from __future__ import annotations

import hashlib
from pathlib import Path

from oh_my_harness.kb.cli._remote import (
    RAW_BASE_URL,
    WorkflowEntry,
    fetch_text,
)


def workflows_dest_root(home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / ".claude" / "workflows"


def local_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workflow_status(entry: WorkflowEntry, dest_root: Path) -> str:
    """Return 'up-to-date', 'not-installed', or 'drift'."""
    dest = dest_root / f"{entry.name}.ts"
    if not dest.exists():
        return "not-installed"
    if local_sha256(dest) != entry.sha256:
        return "drift"
    return "up-to-date"


def local_version(entry: WorkflowEntry, dest_root: Path) -> str:
    """Return the local version string, or '(none)' if not installed."""
    dest = dest_root / f"{entry.name}.ts"
    if not dest.exists():
        return "(none)"
    # Workflows are .ts files — no frontmatter; return the manifest version
    # as a best-effort (no local version extraction possible without parsing TS).
    return entry.version


def pull_workflow(entry: WorkflowEntry, dest_root: Path) -> None:
    """Download a single workflow .ts file."""
    url = f"{RAW_BASE_URL}/{entry.path}"
    content = fetch_text(url)
    dest = dest_root / f"{entry.name}.ts"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def pull_all_workflows(dest_root: Path | None = None) -> tuple[int, list[str]]:
    """Pull all workflows from the remote manifest. Returns (count, errors)."""
    from oh_my_harness.kb.cli._remote import load_remote_manifest

    root = dest_root if dest_root is not None else workflows_dest_root()
    errors: list[str] = []
    count = 0
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        return 0, [str(exc)]
    for entry in manifest.workflows:
        try:
            pull_workflow(entry, root)
            count += 1
        except RuntimeError as exc:
            errors.append(f"{entry.name}: {exc}")
    return count, errors
