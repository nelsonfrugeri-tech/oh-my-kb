"""Tests for ``omk universe`` commands via Typer's CliRunner.

Drives the real ``app`` object end-to-end against a temp config dir and a
real ``QdrantStore`` pointed at the in-memory backend (so we exercise the
typer wiring and the collection_name_for contract without ever touching
Docker).
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
    for cmd in ("install", "universe", "help"):
        assert cmd in result.output


def test_dash_dash_help_also_works(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "install" in result.output
    assert "universe" in result.output


# --- universe create ---------------------------------------------------


def test_universe_create_writes_config_and_creates_dir(
    runner: CliRunner, isolated_env: Path
) -> None:
    result = runner.invoke(app, ["universe", "create", "research"])

    assert result.exit_code == 0, result.output
    cfg = load_config()
    assert cfg.has("research")
    universe = cfg.get("research")
    assert universe is not None
    assert universe.collection == collection_name_for("research")
    assert universe.notes_root.is_dir()


def test_universe_create_duplicate_returns_error(
    runner: CliRunner, isolated_env: Path
) -> None:
    runner.invoke(app, ["universe", "create", "default"])
    result = runner.invoke(app, ["universe", "create", "default"])

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_universe_create_with_explicit_notes_root(
    runner: CliRunner, isolated_env: Path, tmp_path: Path
) -> None:
    custom = tmp_path / "elsewhere"
    result = runner.invoke(
        app, ["universe", "create", "custom", "--notes-root", str(custom)]
    )

    assert result.exit_code == 0, result.output
    cfg = load_config()
    universe = cfg.get("custom")
    assert universe is not None
    assert universe.notes_root == custom
    assert custom.is_dir()


# --- universe list -----------------------------------------------------


def test_universe_list_empty_state(runner: CliRunner, isolated_env: Path) -> None:
    result = runner.invoke(app, ["universe", "list"])
    assert result.exit_code == 0
    assert "no universes" in result.output.lower()


def test_universe_list_marks_active_with_star(
    runner: CliRunner, isolated_env: Path
) -> None:
    runner.invoke(app, ["universe", "create", "alpha"])
    runner.invoke(app, ["universe", "create", "beta"])
    runner.invoke(app, ["universe", "use", "beta"])

    result = runner.invoke(app, ["universe", "list"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    alpha_line = next(line for line in lines if "alpha" in line)
    beta_line = next(line for line in lines if "beta" in line)
    assert "*" in beta_line
    assert "*" not in alpha_line


# --- universe use ------------------------------------------------------


def test_universe_use_changes_active(runner: CliRunner, isolated_env: Path) -> None:
    runner.invoke(app, ["universe", "create", "alpha"])
    runner.invoke(app, ["universe", "create", "beta"])

    result = runner.invoke(app, ["universe", "use", "beta"])

    assert result.exit_code == 0, result.output
    assert load_config().active == "beta"


def test_universe_use_unknown_returns_error(
    runner: CliRunner, isolated_env: Path
) -> None:
    result = runner.invoke(app, ["universe", "use", "nope"])
    assert result.exit_code != 0
    assert "not configured" in result.output
