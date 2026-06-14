"""SessionStart hook management for harness settings files.

This module provides idempotent read/mutate/write operations for
``~/.claude/settings.json`` (and future harness equivalents) so that
``omh install`` can register a SessionStart hook that prompts the model
to run the ``/drink_context`` slash command at the start of every session.

Design decisions
----------------
Hook format
    We use a ``command`` hook that prints a sentinel line to stdout.
    Claude Code reads this output and the model sees it as a system message.
    The command is::

        echo '# omh-managed: drink_context — run /drink_context to load project context'

    Why ``echo`` instead of directly injecting a tool call:
    - Directly auto-running a slash command from a hook is not officially supported.
    - Printing a message that tells the model to run ``/drink_context`` is the
      safest, most portable approach. The model reads the hook output and acts on it
      during its first turn.
    - This is explicitly documented as the SAFEST option in the PR spec.

Idempotency sentinel
    The hook command is prefixed with ``# omh-managed: drink_context``.
    Any hook whose ``command`` starts with this prefix is considered ours.
    Installing twice does NOT duplicate the hook — we find our entry and
    update it in-place.

Atomic writes
    We write to a ``<path>.tmp`` file first and then call ``os.replace``
    (atomic on POSIX) so a crash mid-write never corrupts the original.

Harness support
    Only ``claude-code`` is supported for now.  Other harnesses return a
    "skipped" report.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

SessionStartAction = Literal["installed", "already_present", "skipped", "removed"]


@dataclass(frozen=True, slots=True)
class SessionStartReport:
    """Result of :func:`install_session_start` or :func:`uninstall_session_start`."""

    action: SessionStartAction
    settings_path: Path
    reason: str | None = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# This prefix is the idempotency sentinel — any hook whose ``command`` starts
# with this string is considered managed by omh and will not be duplicated.
_OMH_HOOK_PREFIX: str = "# omh-managed: drink_context"

# The full command written into settings.json.  It prints a single line that
# the model reads as a system message instructing it to call /drink_context.
_OMH_HOOK_COMMAND: str = (
    "echo '# omh-managed: drink_context"
    " — run /drink_context to load the project context for this session.'"
)

# The timeout (ms) for the hook command itself.
_OMH_HOOK_TIMEOUT_MS: int = 5000

# Harnesses that support SessionStart hooks via settings.json.
_SUPPORTED_HARNESSES: frozenset[str] = frozenset({"claude-code"})


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class UnsupportedHarnessError(ValueError):
    """Raised when *harness* does not support SessionStart hooks."""


def settings_path_for(harness: str) -> Path:
    """Return the settings.json path for *harness*.

    Args:
        harness: Harness name (e.g. ``"claude-code"``).

    Returns:
        Absolute :class:`Path` to the settings file.

    Raises:
        UnsupportedHarnessError: if *harness* does not support SessionStart hooks.
    """
    if harness not in _SUPPORTED_HARNESSES:
        raise UnsupportedHarnessError(
            f"harness '{harness}' does not support SessionStart hooks via settings.json; "
            f"supported: {sorted(_SUPPORTED_HARNESSES)}"
        )
    return Path.home() / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# Pure helper functions (testable without I/O)
# ---------------------------------------------------------------------------


def _load_settings(path: Path) -> dict[str, Any]:
    """Load *path* as JSON, returning ``{}`` if missing or empty.

    Raises:
        json.JSONDecodeError: if the file exists but contains invalid JSON.
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    # Let JSONDecodeError propagate — callers must not silently swallow it.
    result: dict[str, Any] = json.loads(text)
    return result


def _find_omh_hook_index(hooks_list: list[dict[str, Any]]) -> int:
    """Return the index of our managed hook entry in *hooks_list*, or -1.

    Detection uses ``in`` rather than ``startswith`` because the command is
    wrapped in an ``echo '...'`` shell expression; the sentinel prefix appears
    inside the command string.
    """
    for i, entry in enumerate(hooks_list):
        for h in entry.get("hooks", []):
            if isinstance(h.get("command"), str) and _OMH_HOOK_PREFIX in h["command"]:
                return i
    return -1


def _build_omh_hook_entry() -> dict[str, Any]:
    """Return the hook entry dict to insert/replace in the SessionStart list."""
    return {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": _OMH_HOOK_COMMAND,
                "timeout": _OMH_HOOK_TIMEOUT_MS,
            }
        ],
    }


def _mutate_install(settings: dict[str, Any]) -> tuple[dict[str, Any], SessionStartAction]:
    """Return *(updated_settings, action)* with the omh hook installed.

    This is a pure function — it does not touch the filesystem.
    """
    # Ensure "hooks" → "SessionStart" exists as a list.
    hooks_section: dict[str, Any] = settings.setdefault("hooks", {})
    session_start: list[dict[str, Any]] = hooks_section.setdefault("SessionStart", [])

    idx = _find_omh_hook_index(session_start)
    entry = _build_omh_hook_entry()

    if idx == -1:
        session_start.append(entry)
        action: SessionStartAction = "installed"
    else:
        existing = session_start[idx]
        if existing == entry:
            action = "already_present"
        else:
            session_start[idx] = entry
            action = "installed"

    return settings, action


def _mutate_uninstall(
    settings: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Return *(updated_settings, was_removed)* with the omh hook removed.

    This is a pure function — it does not touch the filesystem.
    """
    hooks_section: dict[str, Any] = settings.get("hooks", {})
    session_start: list[dict[str, Any]] = hooks_section.get("SessionStart", [])

    idx = _find_omh_hook_index(session_start)
    if idx == -1:
        return settings, False

    session_start.pop(idx)

    # Clean up empty SessionStart and hooks sections to keep the file tidy.
    if not session_start:
        hooks_section.pop("SessionStart", None)
    if not hooks_section:
        settings.pop("hooks", None)

    return settings, True


def _write_settings_atomic(path: Path, settings: dict[str, Any]) -> None:
    """Write *settings* to *path* atomically (temp file + rename).

    The parent directory is created if it does not exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a sibling temp file, then atomically replace.
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".settings_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        # Clean up the temp file if anything goes wrong.
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_session_start(
    harness: str,
    *,
    home: Path | None = None,
) -> SessionStartReport:
    """Idempotently install the omh SessionStart hook for *harness*.

    For ``claude-code``, modifies ``~/.claude/settings.json``.
    For unsupported harnesses, returns a "skipped" report without touching any file.

    Args:
        harness: Harness name (e.g. ``"claude-code"``).
        home: Override for :func:`Path.home` — used in tests to avoid touching
            the real ``~/.claude/settings.json``.

    Returns:
        :class:`SessionStartReport` with ``action``, ``settings_path``, and
        optional ``reason``.
    """
    if harness not in _SUPPORTED_HARNESSES:
        # Return a fake but safe path for the report.
        fake_path = (home or Path.home()) / ".claude" / "settings.json"
        return SessionStartReport(
            action="skipped",
            settings_path=fake_path,
            reason=f"harness '{harness}' does not support SessionStart hooks",
        )

    from unittest.mock import patch

    if home is not None:
        with patch.object(Path, "home", return_value=home):
            return _do_install_session_start(harness)
    return _do_install_session_start(harness)


def _do_install_session_start(harness: str) -> SessionStartReport:
    """Internal implementation after home override has been applied."""
    path = settings_path_for(harness)
    settings = _load_settings(path)
    updated, action = _mutate_install(settings)
    if action != "already_present":
        _write_settings_atomic(path, updated)
    return SessionStartReport(action=action, settings_path=path)


def uninstall_session_start(
    harness: str,
    *,
    home: Path | None = None,
) -> SessionStartReport:
    """Remove the omh SessionStart hook from *harness*'s settings file.

    Idempotent: returns "skipped" if the hook is not present or harness is unsupported.

    Args:
        harness: Harness name (e.g. ``"claude-code"``).
        home: Override for :func:`Path.home` — used in tests.

    Returns:
        :class:`SessionStartReport` with ``action`` set to ``"installed"``
        (we reuse this action to mean "removed" for the uninstall case),
        ``"skipped"`` (nothing was there), or ``"skipped"`` (unsupported harness).
    """
    if harness not in _SUPPORTED_HARNESSES:
        fake_path = (home or Path.home()) / ".claude" / "settings.json"
        return SessionStartReport(
            action="skipped",
            settings_path=fake_path,
            reason=f"harness '{harness}' does not support SessionStart hooks",
        )

    from unittest.mock import patch

    if home is not None:
        with patch.object(Path, "home", return_value=home):
            return _do_uninstall_session_start(harness)
    return _do_uninstall_session_start(harness)


def _do_uninstall_session_start(harness: str) -> SessionStartReport:
    """Internal implementation after home override has been applied."""
    path = settings_path_for(harness)
    settings = _load_settings(path)
    updated, was_removed = _mutate_uninstall(settings)
    if was_removed:
        _write_settings_atomic(path, updated)
        return SessionStartReport(
            action="removed",
            settings_path=path,
            reason="hook removed",
        )
    return SessionStartReport(
        action="skipped",
        settings_path=path,
        reason="hook was not present",
    )
