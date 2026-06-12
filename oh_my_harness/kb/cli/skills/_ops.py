"""Shared skill operations used by list/pull/diff/update commands."""

from __future__ import annotations

import hashlib
from pathlib import Path

from oh_my_harness.kb.cli._remote import (
    RAW_BASE_URL,
    SkillEntry,
    fetch_text,
)


def skills_dest_root(home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / ".claude" / "skills"


def local_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def skill_status(entry: SkillEntry, dest_root: Path) -> str:
    """Return 'up-to-date', 'not-installed', 'drift', or 'update-available'."""
    skill_dir = dest_root / entry.name
    if not skill_dir.exists():
        return "not-installed"
    for f in entry.files:
        local = skill_dir / f.path
        if local_sha256(local) != f.sha256:
            return "drift"
    return "up-to-date"


def local_version(entry: SkillEntry, dest_root: Path) -> str:
    """Read version from SKILL.md frontmatter, or '(none)' if not installed."""
    skill_md = dest_root / entry.name / "SKILL.md"
    if not skill_md.exists():
        return "(none)"
    try:
        import frontmatter as fm
        post = fm.load(str(skill_md))
        return str(post.metadata.get("version", "(none)"))
    except Exception:
        return "(none)"


def pull_skill(entry: SkillEntry, dest_root: Path) -> int:
    """Download all files for a skill. Returns number of files written."""
    count = 0
    skill_dir = dest_root / entry.name
    for f in entry.files:
        url = f"{RAW_BASE_URL}/{entry.path}/{f.path}"
        content = fetch_text(url)
        dest = skill_dir / f.path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        count += 1
    return count


def pull_all_skills(dest_root: Path | None = None) -> tuple[int, list[str]]:
    """Pull all skills from the remote manifest. Returns (count, errors)."""
    from oh_my_harness.kb.cli._remote import load_remote_manifest

    root = dest_root if dest_root is not None else skills_dest_root()
    errors: list[str] = []
    count = 0
    try:
        manifest = load_remote_manifest()
    except RuntimeError as exc:
        return 0, [str(exc)]
    for entry in manifest.skills:
        try:
            count += pull_skill(entry, root)
        except RuntimeError as exc:
            errors.append(f"{entry.name}: {exc}")
    return count, errors
