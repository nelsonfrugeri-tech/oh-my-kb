"""Shared agent operations used by list/pull/diff/update commands."""

from __future__ import annotations

import hashlib
from pathlib import Path

from oh_my_harness.kb.cli._remote import (
    RAW_BASE_URL,
    AgentEntry,
    fetch_text,
)


def agents_dest_root(home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / ".claude" / "agents"


def local_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def agent_status(entry: AgentEntry, dest_root: Path) -> str:
    """Return 'up-to-date', 'not-installed', or 'drift'."""
    dest = dest_root / f"{entry.name}.md"
    if not dest.exists():
        return "not-installed"
    if local_sha256(dest) != entry.sha256:
        return "drift"
    return "up-to-date"


def local_version(entry: AgentEntry, dest_root: Path) -> str:
    """Read version from agent .md frontmatter, or '(none)' if not installed."""
    dest = dest_root / f"{entry.name}.md"
    if not dest.exists():
        return "(none)"
    try:
        import frontmatter as fm
        post = fm.load(str(dest))
        return str(post.metadata.get("version", "(none)"))
    except Exception:
        return "(none)"


def pull_agent(entry: AgentEntry, dest_root: Path) -> None:
    """Download a single agent .md file."""
    url = f"{RAW_BASE_URL}/{entry.path}"
    content = fetch_text(url)
    dest = dest_root / f"{entry.name}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def pull_all_agents(dest_root: Path | None = None) -> tuple[int, list[str]]:
    """Pull all agents from the remote manifest. Returns (count, errors)."""
    from oh_my_harness.kb.cli._remote import load_remote_manifest

    root = dest_root if dest_root is not None else agents_dest_root()
    errors: list[str] = []
    count = 0
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        return 0, [str(exc)]
    for entry in manifest.agents:
        try:
            pull_agent(entry, root)
            count += 1
        except RuntimeError as exc:
            errors.append(f"{entry.name}: {exc}")
    return count, errors
