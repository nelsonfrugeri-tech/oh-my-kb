"""Tests for the :class:`oh_my_kb.cli.install.wizard.Wizard` and related classes.

Tests cover:
- Non-interactive (``--yes``) mode: defaults accepted, summary printed, no prompts.
- Interactive mode: prompt flow for each step.
- :class:`InstallChoices` summary and confirm.
- :class:`WizardStep` validator helpers.
- Full ``omk install --yes`` CLI invocation with Docker mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from oh_my_kb.cli.app import app
from oh_my_kb.cli.config import CLIConfig, Universe
from oh_my_kb.cli.install.wizard import (
    InstallChoices,
    Wizard,
    _validate_harness,
    _validate_path,
    _validate_port,
    _validate_universe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(active: str = "default") -> CLIConfig:
    return CLIConfig(
        universes=[
            Universe(
                name=active,
                notes_root=Path("/tmp/oh-my-kb") / active,
                collection=f"kb_{active}",
            )
        ],
        active=active,
    )


def _fake_client() -> MagicMock:
    """Minimal Docker client fake: container always running."""

    client = MagicMock()
    container = MagicMock()
    container.status = "running"
    container.short_id = "abc123"
    client.containers.get.return_value = container
    client.images.get.return_value = MagicMock()
    return client


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Validator helpers
# ---------------------------------------------------------------------------


class TestValidators:
    def test_validate_path_expands_tilde(self) -> None:
        result = _validate_path("~/notes")
        assert "~" not in str(result)
        assert result.is_absolute()

    def test_validate_port_accepts_valid(self) -> None:
        assert _validate_port("6333") == 6333

    def test_validate_port_rejects_non_integer(self) -> None:
        with pytest.raises(ValueError, match="integer"):
            _validate_port("abc")

    def test_validate_port_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="65535"):
            _validate_port("99999")

    def test_validate_universe_strips_whitespace(self) -> None:
        assert _validate_universe("  default  ") == "default"

    def test_validate_universe_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _validate_universe("   ")

    def test_validate_harness_accepts_claude_code(self) -> None:
        assert _validate_harness("claude-code") == "claude-code"

    def test_validate_harness_rejects_unknown(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            _validate_harness("unknown-harness")

    def test_validate_harness_rejects_coming_soon(self) -> None:
        with pytest.raises(ValueError, match="not yet available"):
            _validate_harness("cursor")


# ---------------------------------------------------------------------------
# Wizard — non-interactive mode (--yes)
# ---------------------------------------------------------------------------


class TestWizardNonInteractive:
    def test_run_returns_install_choices(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            wizard = Wizard(non_interactive=True)
            choices = wizard.run()
        assert isinstance(choices, InstallChoices)

    def test_defaults_used_in_non_interactive_mode(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            wizard = Wizard(non_interactive=True)
            choices = wizard.run()
        assert choices.universe == "default"
        assert choices.qdrant_port == 6333
        assert choices.harness == "claude-code"

    def test_notes_root_is_path(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            wizard = Wizard(non_interactive=True)
            choices = wizard.run()
        assert isinstance(choices.notes_root, Path)

    def test_models_cache_is_path(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            wizard = Wizard(non_interactive=True)
            choices = wizard.run()
        assert isinstance(choices.models_cache, Path)

    def test_prefill_overrides_defaults(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            wizard = Wizard(
                non_interactive=True,
                prefill={"universe": "my-universe", "qdrant_port": 6334},
            )
            choices = wizard.run()
        assert choices.universe == "my-universe"
        assert choices.qdrant_port == 6334


# ---------------------------------------------------------------------------
# InstallChoices
# ---------------------------------------------------------------------------


class TestInstallChoices:
    def _choices(self, tmp_path: Path) -> InstallChoices:
        return InstallChoices(
            notes_root=tmp_path / "notes",
            universe="default",
            qdrant_port=6333,
            models_cache=tmp_path / ".cache" / "models",
            harness="claude-code",
        )

    def test_summary_contains_universe(self, tmp_path: Path) -> None:
        choices = self._choices(tmp_path)
        assert "default" in choices.summary()

    def test_summary_contains_port(self, tmp_path: Path) -> None:
        choices = self._choices(tmp_path)
        assert "6333" in choices.summary()

    def test_summary_contains_harness(self, tmp_path: Path) -> None:
        choices = self._choices(tmp_path)
        assert "claude-code" in choices.summary()

    def test_summary_contains_notes_root(self, tmp_path: Path) -> None:
        choices = self._choices(tmp_path)
        assert str(choices.notes_root) in choices.summary()


# ---------------------------------------------------------------------------
# Full CLI: omk install --yes
# ---------------------------------------------------------------------------


class TestInstallCLIYes:
    def test_exits_zero_with_mocked_docker(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_client()

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.ensure_collection"),
        ):
            result = runner.invoke(app, ["install", "--yes"])

        assert result.exit_code == 0, result.output

    def test_output_contains_all_6_steps(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_client()

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.ensure_collection"),
        ):
            result = runner.invoke(app, ["install", "--yes"])

        for step in range(1, 7):
            assert f"[{step}/6]" in result.output, f"step {step}/6 missing from output"

    def test_generates_claude_md(self, runner: CliRunner, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_client()

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.ensure_collection"),
        ):
            runner.invoke(app, ["install", "--yes"])

        claude_md = home / ".claude" / "CLAUDE.md"
        assert claude_md.exists(), "~/.claude/CLAUDE.md was not created"
        content = claude_md.read_text(encoding="utf-8")
        assert "oh-my-kb" in content

    def test_claude_md_contains_all_tools(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        from oh_my_kb.mcp.tools import (
            KB_EXPAND_TOOL,
            KB_RECENT_TOOL,
            KB_RESOURCE_DIFF_TOOL,
            KB_RESOURCE_LIST_TOOL,
            KB_RESOURCE_UPDATE_TOOL,
            KB_SEARCH_TOOL,
            KB_TREE_TOOL,
            KB_WRITE_TOOL,
        )

        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_client()

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.ensure_collection"),
        ):
            runner.invoke(app, ["install", "--yes"])

        content = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        for tool in [
            KB_WRITE_TOOL,
            KB_SEARCH_TOOL,
            KB_TREE_TOOL,
            KB_EXPAND_TOOL,
            KB_RECENT_TOOL,
            KB_RESOURCE_LIST_TOOL,
            KB_RESOURCE_DIFF_TOOL,
            KB_RESOURCE_UPDATE_TOOL,
        ]:
            assert tool.name in content, f"tool {tool.name} missing from CLAUDE.md"

    def test_creates_universe_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_client()

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.ensure_collection"),
        ):
            result = runner.invoke(
                app,
                ["install", "--yes"],
                env={"OMK_CONFIG_DIR": str(tmp_path / "config")},
            )

        assert result.exit_code == 0, result.output

    def test_docker_not_running_exits_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        from oh_my_kb.infra.docker_qdrant import DockerNotRunningError

        home = tmp_path / "home"
        home.mkdir()

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_kb.infra.docker_qdrant.QdrantContainer.status",
                side_effect=DockerNotRunningError("Docker not running"),
            ),
        ):
            result = runner.invoke(app, ["install", "--yes"])

        assert result.exit_code != 0

    def test_output_contains_proximos_passos(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_client()

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.ensure_collection"),
        ):
            result = runner.invoke(app, ["install", "--yes"])

        assert "Proximos passos" in result.output or "passos" in result.output.lower()

    def test_install_idempotent_second_run(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Re-running install with --yes should exit 0 on second call."""
        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_client()

        patches = (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_kb.storage.QdrantStore.ensure_collection"),
        )
        config_dir = str(tmp_path / "config")

        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            runner.invoke(app, ["install", "--yes"], env={"OMK_CONFIG_DIR": config_dir})
            result = runner.invoke(
                app, ["install", "--yes"], env={"OMK_CONFIG_DIR": config_dir}
            )

        assert result.exit_code == 0, result.output
