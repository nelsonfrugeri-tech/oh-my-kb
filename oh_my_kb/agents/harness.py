"""Harness registry — maps harness names to their target file and detection signal."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Harness:
    name: str
    target_filename: str
    detection_signal: str | None


HARNESS_REGISTRY: dict[str, Harness] = {
    "claude-code": Harness("claude-code", "CLAUDE.md", ".claude"),
    "claude-desktop": Harness("claude-desktop", "CLAUDE.md", None),
}


class UnknownHarnessError(ValueError):
    """Raised when harness name is not in HARNESS_REGISTRY."""


def resolve_harness(name: str) -> Harness:
    """Return the :class:`Harness` for *name*, raising :class:`UnknownHarnessError` if absent."""
    try:
        return HARNESS_REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(HARNESS_REGISTRY))
        raise UnknownHarnessError(f"unknown harness '{name}'; known: {known}") from None


def target_path_for(harness: Harness, project_path: Path) -> Path:
    """Return the absolute path to the harness rules file within *project_path*."""
    return project_path / harness.target_filename
