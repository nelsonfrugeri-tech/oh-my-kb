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
    universe: str
    target_file: Path
    action: InjectAction
    bytes_written: int


class NoActiveUniverseError(ValueError):
    """Raised when no active universe is configured."""


def do_bootstrap(
    harness: str,
    universe: str,
    *,
    home: Path | None = None,
) -> BootstrapReport:
    """Single entry point for the wizard (step 6) and ``omk resource update``.

    Orchestrates: ``resolve_harness`` → ``render_dynamic_block`` →
    ``inject_block`` → write.

    Args:
        harness: Harness name (e.g. ``"claude-code"``).
        universe: Active universe name.
        home: Override for :func:`Path.home` — used in tests to avoid
            touching the real ``~/.claude/CLAUDE.md``.  When provided the
            override is applied for the duration of the call only.

    Returns:
        :class:`BootstrapReport` with ``target``, ``action``, and
        ``bytes_written``.
    """
    from unittest.mock import patch

    project_path = Path.cwd()
    if home is not None:
        with patch.object(Path, "home", return_value=home):
            return bootstrap(harness=harness, project_path=project_path, active_universe=universe)
    return bootstrap(harness=harness, project_path=project_path, active_universe=universe)


def bootstrap(
    *,
    harness: str,
    project_path: Path,
    active_universe: str | None,
) -> BootstrapReport:
    """Inject the kb-mcp rules block into *harness*'s target file.

    For *global* harnesses (e.g. ``claude-code``) the target is always
    ``~/.claude/CLAUDE.md`` regardless of *project_path*.  For *project*
    harnesses the target lives under *project_path*.

    Raises:
        NoActiveUniverseError: if ``active_universe`` is ``None``.
        UnknownHarnessError: if *harness* is not in :data:`HARNESS_REGISTRY`.
        FileNotFoundError: if *project_path* does not exist or is not a directory
            (only checked for *project*-scoped harnesses).
    """
    if active_universe is None:
        raise NoActiveUniverseError("no active universe; run `omk install` first")

    h = resolve_harness(harness)  # raises UnknownHarnessError if unknown

    if h.scope == "project" and not project_path.is_dir():
        raise FileNotFoundError(
            f"project path does not exist or is not a directory: {project_path}"
        )

    target = target_path_for(h, project_path)

    # For global harnesses, ensure the parent directory exists (Bug 4 fix: safe creation).
    if h.scope == "global":
        target.parent.mkdir(parents=True, exist_ok=True)

    new_block = render_dynamic_block(active_universe)
    wrapped_block = f"{START_MARKER}\n{new_block.rstrip()}\n{END_MARKER}\n"

    current = target.read_text(encoding="utf-8") if target.exists() else None
    new_content, action = inject_block(current, new_block)

    if action != InjectAction.UNCHANGED:
        target.write_text(new_content, encoding="utf-8")

    return BootstrapReport(
        harness=h.name,
        universe=active_universe,
        target_file=target,
        action=action,
        bytes_written=len(wrapped_block.encode("utf-8")),
    )
