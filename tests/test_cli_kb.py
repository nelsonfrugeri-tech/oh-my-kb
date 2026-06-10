"""Tests for ``omk kb`` commands via Typer's CliRunner.

Drives the real ``app`` object end-to-end against a temp config dir and a
real ``QdrantStore`` pointed at the in-memory backend (so we exercise the
typer wiring and the collection_name_for contract without ever touching
Docker).

Note on naming: the CLI surface uses ``kb`` (the user-facing subgroup introduced
in issue #55), while the underlying domain model retains the name ``universe``.
Test functions use the ``test_kb_*`` prefix to match the CLI surface; internal
variables may still refer to ``universe`` objects as that is what the model
returns.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from oh_my_kb.cli.app import app
from oh_my_kb.cli.config import CONFIG_DIR_ENV, load_config
from oh_my_kb.cli.paths import DATA_ROOT_ENV
from oh_my_kb.services import collection_name_for
from oh_my_kb.storage import IN_MEMORY


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path / "config"))
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path / "data"))
    monkeypatch.setenv("KB_QDRANT_URL", IN_MEMORY)
    return tmp_path


# --- help --------------------------------------------------------------


def test_help_lists_top_level_commands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["help"])
    assert result.exit_code == 0
    for cmd in ("install", "kb", "help"):
        assert cmd in result.output
    assert "universe" not in result.output.lower()


def test_dash_dash_help_also_works(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "install" in result.output
    assert "kb" in result.output
    assert "universe" not in result.output.lower()


# --- kb create ---------------------------------------------------


def test_kb_create_writes_config_and_creates_dir(
    runner: CliRunner, isolated_env: Path
) -> None:
    result = runner.invoke(app, ["kb", "create", "research"])

    assert result.exit_code == 0, result.output
    cfg = load_config()
    assert cfg.has("research")
    universe = cfg.get("research")
    assert universe is not None
    assert universe.collection == collection_name_for("research")
    assert universe.notes_root.is_dir()


def test_kb_create_handles_qdrant_offline(
    runner: CliRunner, isolated_env: Path
) -> None:
    """When QdrantStore.ensure_collection raises, exit 1 with a friendly message."""
    from unittest.mock import patch

    with patch(
        "oh_my_kb.cli.app.QdrantStore.ensure_collection",
        side_effect=RuntimeError("connection refused"),
    ):
        result = runner.invoke(app, ["kb", "create", "test-qa"])

    assert result.exit_code == 1
    # Default CliRunner mixes stderr into output; check for the user-friendly hint.
    assert "omk start" in result.output or "Docker" in result.output


def test_kb_create_duplicate_returns_error(
    runner: CliRunner, isolated_env: Path
) -> None:
    runner.invoke(app, ["kb", "create", "default"])
    result = runner.invoke(app, ["kb", "create", "default"])

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_kb_create_with_explicit_notes_root(
    runner: CliRunner, isolated_env: Path, tmp_path: Path
) -> None:
    custom = tmp_path / "elsewhere"
    result = runner.invoke(
        app, ["kb", "create", "custom", "--notes-root", str(custom)]
    )

    assert result.exit_code == 0, result.output
    cfg = load_config()
    universe = cfg.get("custom")
    assert universe is not None
    assert universe.notes_root == custom
    assert custom.is_dir()


# --- kb list -----------------------------------------------------


def test_kb_list_empty_state(runner: CliRunner, isolated_env: Path) -> None:
    result = runner.invoke(app, ["kb", "list"])
    assert result.exit_code == 0
    assert "no knowledge bases" in result.output.lower()


def test_kb_list_marks_active_with_star(
    runner: CliRunner, isolated_env: Path
) -> None:
    runner.invoke(app, ["kb", "create", "alpha"])
    runner.invoke(app, ["kb", "create", "beta"])
    runner.invoke(app, ["kb", "use", "beta"])

    result = runner.invoke(app, ["kb", "list"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    alpha_line = next(line for line in lines if "alpha" in line)
    beta_line = next(line for line in lines if "beta" in line)
    assert "*" in beta_line
    assert "*" not in alpha_line


# --- kb use ------------------------------------------------------


def test_kb_use_changes_active(runner: CliRunner, isolated_env: Path) -> None:
    runner.invoke(app, ["kb", "create", "alpha"])
    runner.invoke(app, ["kb", "create", "beta"])

    result = runner.invoke(app, ["kb", "use", "beta"])

    assert result.exit_code == 0, result.output
    assert load_config().active == "beta"


def test_kb_use_unknown_returns_error(
    runner: CliRunner, isolated_env: Path
) -> None:
    result = runner.invoke(app, ["kb", "use", "nope"])
    assert result.exit_code != 0
    assert "not configured" in result.output
