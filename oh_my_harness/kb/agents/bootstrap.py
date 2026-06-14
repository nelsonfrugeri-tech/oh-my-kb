"""Bootstrap — inject the kb-mcp rules block into a harness rules file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from oh_my_harness.kb.agents.harness import resolve_harness, target_path_for
from oh_my_harness.kb.agents.injector import (
    END_MARKER,
    START_MARKER,
    InjectAction,
    inject_block,
)
from oh_my_harness.kb.agents.template import render_dynamic_block


@dataclass(frozen=True, slots=True)
class BootstrapReport:
    harness: str
    kb_name: str
    target_file: Path
    action: InjectAction
    bytes_written: int

    # Backward-compatible alias — kept so existing call sites that read .universe still work.
    @property
    def universe(self) -> str:  # backward-compatible alias
        return self.kb_name


class NoActiveKbError(ValueError):
    """Raised when no active knowledge base is configured."""


# Backward-compatible alias.
NoActiveUniverseError = NoActiveKbError  # backward-compatible alias


def do_bootstrap(
    harness: str,
    kb_name: str,
    *,
    home: Path | None = None,
) -> BootstrapReport:
    """Single entry point for the wizard (step 6) and ``omh`` resource commands.

    Orchestrates: ``resolve_harness`` → ``render_dynamic_block`` →
    ``inject_block`` → write.

    Args:
        harness: Harness name (e.g. ``"claude-code"``).
        kb_name: Active knowledge base name.
        home: Override for :func:`Path.home` — used in tests to avoid
            touching the real ``~/.claude/CLAUDE.md``.  When provided the
            override is applied for the duration of the call only.

    Returns:
        :class:`BootstrapReport` with ``target_file``, ``action``, and
        ``bytes_written``.
    """
    from unittest.mock import patch

    project_path = Path.cwd()
    if home is not None:
        with patch.object(Path, "home", return_value=home):
            return bootstrap(harness=harness, project_path=project_path, active_kb=kb_name)
    return bootstrap(harness=harness, project_path=project_path, active_kb=kb_name)


def bootstrap(
    *,
    harness: str,
    project_path: Path,
    active_kb: str | None = None,
    # Backward-compatible parameter name — maps to active_kb when active_kb is None.
    active_universe: str | None = None,
) -> BootstrapReport:
    """Inject the kb-mcp rules block into *harness*'s target file.

    For *global* harnesses (e.g. ``claude-code``) the target is always
    ``~/.claude/CLAUDE.md`` regardless of *project_path*.  For *project*
    harnesses the target lives under *project_path*.

    Raises:
        NoActiveKbError: if both ``active_kb`` and ``active_universe`` are ``None``.
        UnknownHarnessError: if *harness* is not in :data:`HARNESS_REGISTRY`.
        FileNotFoundError: if *project_path* does not exist or is not a directory
            (only checked for *project*-scoped harnesses).
    """
    # Resolve the kb name from the canonical param, then the legacy alias.
    resolved_kb = active_kb if active_kb is not None else active_universe
    if resolved_kb is None:
        raise NoActiveKbError("no active knowledge base; run `omh install` first")

    h = resolve_harness(harness)  # raises UnknownHarnessError if unknown

    if h.scope == "project" and not project_path.is_dir():
        raise FileNotFoundError(
            f"project path does not exist or is not a directory: {project_path}"
        )

    target = target_path_for(h, project_path)

    # For global harnesses, ensure the parent directory exists.
    if h.scope == "global":
        target.parent.mkdir(parents=True, exist_ok=True)

    new_block = render_dynamic_block(resolved_kb)
    wrapped_block = f"{START_MARKER}\n{new_block.rstrip()}\n{END_MARKER}\n"

    current = target.read_text(encoding="utf-8") if target.exists() else None
    new_content, action = inject_block(current, new_block)

    if action != InjectAction.UNCHANGED:
        target.write_text(new_content, encoding="utf-8")

    return BootstrapReport(
        harness=h.name,
        kb_name=resolved_kb,
        target_file=target,
        action=action,
        bytes_written=len(wrapped_block.encode("utf-8")),
    )
