"""Tests for ``omk start``, ``omk stop``, and ``omk status`` lifecycle commands.

All Docker calls are mocked — no real daemon required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from oh_my_kb.cli.app import app
from oh_my_kb.infra.docker_qdrant import (
    ContainerAction,
    ContainerStatus,
    DockerNotRunningError,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _running_status() -> ContainerStatus:
    return ContainerStatus(
        running=True, image="qdrant/qdrant:latest", port=6333, container_id="abc"
    )


def _stopped_status() -> ContainerStatus:
    return ContainerStatus(
        running=False, image="qdrant/qdrant:latest", port=6333, container_id=None
    )


# ---------------------------------------------------------------------------
# omk start
# ---------------------------------------------------------------------------


class TestStartCmd:
    def test_start_already_running_exits_zero(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.ensure_running",
            return_value=ContainerAction.ALREADY_RUNNING,
        ):
            result = runner.invoke(app, ["start"])
        assert result.exit_code == 0

    def test_start_already_running_prints_message(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.ensure_running",
            return_value=ContainerAction.ALREADY_RUNNING,
        ):
            result = runner.invoke(app, ["start"])
        assert "already running" in result.output.lower()

    def test_start_created_exits_zero(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.ensure_running",
            return_value=ContainerAction.CREATED,
        ):
            result = runner.invoke(app, ["start"])
        assert result.exit_code == 0

    def test_start_created_prints_started_message(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.ensure_running",
            return_value=ContainerAction.CREATED,
        ):
            result = runner.invoke(app, ["start"])
        assert "started" in result.output.lower() or "oh-my-kb-qdrant" in result.output.lower()

    def test_start_docker_not_running_exits_nonzero(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.ensure_running",
            side_effect=DockerNotRunningError("Docker not running"),
        ):
            result = runner.invoke(app, ["start"])
        assert result.exit_code != 0

    def test_start_docker_not_running_prints_error(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.ensure_running",
            side_effect=DockerNotRunningError("Docker not running"),
        ):
            result = runner.invoke(app, ["start"])
        assert "error" in result.output.lower() or "docker" in result.output.lower()


# ---------------------------------------------------------------------------
# omk stop
# ---------------------------------------------------------------------------


class TestStopCmd:
    def test_stop_running_container_exits_zero(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.stop",
            return_value=True,
        ):
            result = runner.invoke(app, ["stop"])
        assert result.exit_code == 0

    def test_stop_running_container_prints_stopped(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.stop",
            return_value=True,
        ):
            result = runner.invoke(app, ["stop"])
        assert "stopped" in result.output.lower() or "oh-my-kb-qdrant" in result.output

    def test_stop_not_running_exits_zero(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.stop",
            return_value=False,
        ):
            result = runner.invoke(app, ["stop"])
        assert result.exit_code == 0

    def test_stop_not_running_prints_not_running(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.stop",
            return_value=False,
        ):
            result = runner.invoke(app, ["stop"])
        assert "not running" in result.output.lower()

    def test_stop_docker_not_running_exits_nonzero(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.stop",
            side_effect=DockerNotRunningError("Docker not running"),
        ):
            result = runner.invoke(app, ["stop"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# omk status
# ---------------------------------------------------------------------------


class TestStatusCmd:
    def test_status_exits_zero(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.status",
            return_value=_running_status(),
        ):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0

    def test_status_shows_container_name(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.status",
            return_value=_running_status(),
        ):
            result = runner.invoke(app, ["status"])
        assert "oh-my-kb-qdrant" in result.output

    def test_status_shows_port(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.status",
            return_value=_running_status(),
        ):
            result = runner.invoke(app, ["status"])
        assert "6333" in result.output

    def test_status_shows_running_state(self, runner: CliRunner) -> None:
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.status",
            return_value=_running_status(),
        ):
            result = runner.invoke(app, ["status"])
        assert "running" in result.output.lower()

    def test_status_docker_not_running_still_exits_zero(
        self, runner: CliRunner
    ) -> None:
        """status command is informational — should not fail hard if Docker is down."""
        with patch(
            "oh_my_kb.infra.docker_qdrant.QdrantContainer.status",
            side_effect=DockerNotRunningError("Docker not running"),
        ):
            result = runner.invoke(app, ["status"])
        # Should still print something useful and exit 0 (informational)
        assert result.exit_code == 0
        assert "docker" in result.output.lower() or "error" in result.output.lower()

    def test_status_shows_version(self, runner: CliRunner) -> None:
        with (
            patch(
                "oh_my_kb.infra.docker_qdrant.QdrantContainer.status",
                return_value=_running_status(),
            ),
            patch(
                "oh_my_kb.cli.lifecycle.importlib.metadata.version",
                return_value="1.2.3",
            ),
        ):
            result = runner.invoke(app, ["status"])
        assert "1.2.3" in result.output
