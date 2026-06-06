"""Bootstrap — inject the kb-mcp rules block into a harness rules file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from oh_my_kb.agents.harness import resolve_harness, target_path_for
from oh_my_kb.agents.injector import (
    END_MARKER,
    START_MARKER,
    InjectAction,
    inject_block,
)
from oh_my_kb.agents.template import render_rules


@dataclass(frozen=True, slots=True)
class BootstrapReport:
    harness: str
    universe: str
    target_file: Path
    action: InjectAction
    bytes_written: int


class NoActiveUniverseError(ValueError):
    """Raised when no active universe is configured."""


def bootstrap(
    *,
    harness: str,
    project_path: Path,
    active_universe: str | None,
) -> BootstrapReport:
    """Inject the kb-mcp rules block into *harness*'s target file.

    Raises:
        NoActiveUniverseError: if ``active_universe`` is ``None``.
        UnknownHarnessError: if *harness* is not in :data:`HARNESS_REGISTRY`.
        FileNotFoundError: if *project_path* does not exist or is not a directory.
    """
    if active_universe is None:
        raise NoActiveUniverseError("no active universe; run `omk install` first")

    h = resolve_harness(harness)  # raises UnknownHarnessError if unknown

    if not project_path.is_dir():
        raise FileNotFoundError(
            f"project path does not exist or is not a directory: {project_path}"
        )

    target = target_path_for(h, project_path)

    new_block = render_rules(active_universe)
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
