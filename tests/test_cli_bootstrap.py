"""Typer CliRunner tests for ``omk bootstrap``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from oh_my_kb.cli.app import app
from oh_my_kb.cli.config import CLIConfig, Universe


def _config(active: str = "test-universe") -> CLIConfig:
    return CLIConfig(
        universes=[
            Universe(
                name=active,
                notes_root=Path("/tmp/oh-my-kb") / active,
                collection=f"kb_{active.replace('-', '_')}",
            )
        ],
        active=active,
    )


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestBootstrapCLISuccess:
    def test_creates_claude_md_and_exits_zero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        with patch("oh_my_kb.cli.app.load_config", return_value=_config()):
            result = runner.invoke(
                app,
                ["bootstrap", "--harness", "claude-code", "--project-path", str(tmp_path)],
            )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "CLAUDE.md").exists()

    def test_success_output_is_green_checkmark(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        with patch("oh_my_kb.cli.app.load_config", return_value=_config()):
            result = runner.invoke(
                app,
                ["bootstrap", "--harness", "claude-code", "--project-path", str(tmp_path)],
            )
        assert result.exit_code == 0
        assert "kb-mcp rules" in result.output

    def test_output_contains_expected_fields(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        with patch("oh_my_kb.cli.app.load_config", return_value=_config("my-universe")):
            result = runner.invoke(
                app,
                ["bootstrap", "--harness", "claude-code", "--project-path", str(tmp_path)],
            )
        assert "universe" in result.output
        assert "target" in result.output
        assert "action" in result.output
        assert "bytes" in result.output


class TestBootstrapCLIErrors:
    def test_unknown_harness_exits_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        with patch("oh_my_kb.cli.app.load_config", return_value=_config()):
            result = runner.invoke(
                app,
                [
                    "bootstrap",
                    "--harness",
                    "unknown-harness",
                    "--project-path",
                    str(tmp_path),
                ],
            )
        assert result.exit_code != 0

    def test_unknown_harness_error_mentions_unknown(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        with patch("oh_my_kb.cli.app.load_config", return_value=_config()):
            result = runner.invoke(
                app,
                [
                    "bootstrap",
                    "--harness",
                    "unknown-harness",
                    "--project-path",
                    str(tmp_path),
                ],
            )
        assert "unknown" in result.output.lower() or "error" in result.output.lower()

    def test_nonexistent_project_path_exits_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        nonexistent = tmp_path / "does-not-exist"
        with patch("oh_my_kb.cli.app.load_config", return_value=_config()):
            result = runner.invoke(
                app,
                [
                    "bootstrap",
                    "--harness",
                    "claude-code",
                    "--project-path",
                    str(nonexistent),
                ],
            )
        assert result.exit_code != 0


class TestBootstrapCLIIdempotent:
    def test_second_run_prints_already_up_to_date(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        with patch("oh_my_kb.cli.app.load_config", return_value=_config()):
            runner.invoke(
                app,
                ["bootstrap", "--harness", "claude-code", "--project-path", str(tmp_path)],
            )
            result = runner.invoke(
                app,
                ["bootstrap", "--harness", "claude-code", "--project-path", str(tmp_path)],
            )
        assert result.exit_code == 0
        assert "already up to date" in result.output
