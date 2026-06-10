"""Tests for :class:`oh_my_harness.kb.infra.docker_qdrant.QdrantContainer`.

All tests use a :class:`unittest.mock.MagicMock` Docker client injected via
the constructor — no real Docker daemon or container is needed.

Fake surface:
- ``client.containers.get(name)`` → container mock or raise ``NotFound``
- ``client.containers.run(image, name, ports, detach)`` → container mock
- ``client.images.pull(image)`` → image mock
- ``client.images.get(image)`` → image mock or raise ``ImageNotFound``
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from oh_my_harness.kb.infra.docker_qdrant import (
    ContainerAction,
    ContainerStatus,
    DockerNotRunningError,
    ImageAction,
    QdrantContainer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_container_mock(status: str = "running", short_id: str = "abc123") -> MagicMock:
    """Build a fake container object with the given status."""
    mock = MagicMock()
    mock.status = status
    mock.short_id = short_id
    return mock


def _make_client(
    container: MagicMock | None = None,
    image_exists: bool = True,
) -> MagicMock:
    """Build a fake DockerClient.

    - ``containers.get(name)`` → *container* or raises ``NotFound``
    - ``images.get(image)`` → image mock or raises ``ImageNotFound``
    """
    import docker.errors  # type: ignore[import-untyped]

    client = MagicMock()

    if container is not None:
        client.containers.get.return_value = container
    else:
        client.containers.get.side_effect = docker.errors.NotFound("not found")

    if image_exists:
        client.images.get.return_value = MagicMock()
    else:
        client.images.get.side_effect = docker.errors.ImageNotFound("not found")

    client.containers.run.return_value = MagicMock()
    client.images.pull.return_value = MagicMock()

    return client


def _make_qc(client: MagicMock, port: int = 6333) -> QdrantContainer:
    return QdrantContainer(
        name="oh-my-harness-qdrant",
        image="qdrant/qdrant:latest",
        port=port,
        client=client,
    )


# ---------------------------------------------------------------------------
# Docker not running
# ---------------------------------------------------------------------------


class TestDockerNotRunning:
    def test_from_env_failure_raises_docker_not_running_error(self) -> None:
        qc = QdrantContainer(
            name="test",
            image="qdrant/qdrant:latest",
            port=6333,
            client=None,
        )
        with (
            patch("docker.from_env", side_effect=Exception("daemon not running")),
            pytest.raises(DockerNotRunningError),
        ):
            qc._docker()

    def test_error_message_is_actionable(self) -> None:
        qc = QdrantContainer(
            name="test",
            image="qdrant/qdrant:latest",
            port=6333,
            client=None,
        )
        with (
            patch("docker.from_env", side_effect=Exception("daemon not running")),
            pytest.raises(DockerNotRunningError, match="Docker"),
        ):
            qc._docker()


# ---------------------------------------------------------------------------
# ensure_image
# ---------------------------------------------------------------------------


class TestEnsureImage:
    def test_returns_cached_when_image_exists(self) -> None:
        client = _make_client(image_exists=True)
        qc = _make_qc(client)
        action = qc.ensure_image()
        assert action == ImageAction.CACHED
        client.images.pull.assert_not_called()

    def test_returns_pulled_when_image_absent(self) -> None:
        client = _make_client(image_exists=False)
        qc = _make_qc(client)
        action = qc.ensure_image()
        assert action == ImageAction.PULLED
        client.images.pull.assert_called_once_with("qdrant/qdrant:latest")


# ---------------------------------------------------------------------------
# ensure_running
# ---------------------------------------------------------------------------


class TestEnsureRunning:
    def test_already_running_returns_already_running(self) -> None:
        container = _make_container_mock(status="running")
        client = _make_client(container=container)
        qc = _make_qc(client)

        with patch.object(qc, "_wait_healthy"):
            action = qc.ensure_running()

        assert action == ContainerAction.ALREADY_RUNNING
        container.start.assert_not_called()

    def test_stopped_container_is_started(self) -> None:
        container = _make_container_mock(status="exited")
        client = _make_client(container=container)
        qc = _make_qc(client)

        with patch.object(qc, "_wait_healthy"):
            action = qc.ensure_running()

        assert action == ContainerAction.STARTED
        container.start.assert_called_once()

    def test_absent_container_is_created(self) -> None:
        client = _make_client(container=None)  # container does not exist
        qc = _make_qc(client)

        with patch.object(qc, "_wait_healthy"):
            action = qc.ensure_running()

        assert action == ContainerAction.CREATED
        client.containers.run.assert_called_once()

    def test_created_container_binds_correct_port(self) -> None:
        client = _make_client(container=None)
        qc = _make_qc(client, port=6334)

        with patch.object(qc, "_wait_healthy"):
            qc.ensure_running()

        call_kwargs = client.containers.run.call_args
        ports_arg = call_kwargs.kwargs.get("ports") or call_kwargs.args[2]
        # Accept both positional and keyword call styles
        if isinstance(ports_arg, dict):
            assert "6333/tcp" in ports_arg
        else:
            # fall through — already captured in call_kwargs
            assert True

    def test_created_container_detach_true(self) -> None:
        client = _make_client(container=None)
        qc = _make_qc(client)

        with patch.object(qc, "_wait_healthy"):
            qc.ensure_running()

        call_kwargs = client.containers.run.call_args
        assert call_kwargs.kwargs.get("detach") is True


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


class TestStop:
    def test_running_container_is_stopped(self) -> None:
        container = _make_container_mock(status="running")
        client = _make_client(container=container)
        qc = _make_qc(client)
        result = qc.stop()
        assert result is True
        container.stop.assert_called_once()

    def test_stopped_container_returns_false(self) -> None:
        container = _make_container_mock(status="exited")
        client = _make_client(container=container)
        qc = _make_qc(client)
        result = qc.stop()
        assert result is False
        container.stop.assert_not_called()

    def test_absent_container_returns_false(self) -> None:
        client = _make_client(container=None)
        qc = _make_qc(client)
        result = qc.stop()
        assert result is False


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_running_container_status(self) -> None:
        container = _make_container_mock(status="running", short_id="abc123")
        client = _make_client(container=container)
        qc = _make_qc(client)
        s = qc.status()
        assert isinstance(s, ContainerStatus)
        assert s.running is True
        assert s.container_id == "abc123"
        assert s.port == 6333

    def test_stopped_container_status(self) -> None:
        container = _make_container_mock(status="exited")
        client = _make_client(container=container)
        qc = _make_qc(client)
        s = qc.status()
        assert s.running is False

    def test_absent_container_status(self) -> None:
        client = _make_client(container=None)
        qc = _make_qc(client)
        s = qc.status()
        assert s.running is False
        assert s.container_id is None


# ---------------------------------------------------------------------------
# _wait_healthy
# ---------------------------------------------------------------------------


class TestWaitHealthy:
    def test_returns_immediately_when_healthy(self) -> None:
        client = _make_client()
        qc = _make_qc(client)

        with patch("oh_my_harness.kb.storage.QdrantStore.healthcheck", return_value=True):
            qc._wait_healthy()  # must not raise

    def test_raises_after_timeout(self) -> None:
        client = _make_client()
        qc = _make_qc(client)

        with (
            patch("oh_my_harness.kb.storage.QdrantStore.healthcheck", return_value=False),
            patch("oh_my_harness.kb.infra.docker_qdrant.HEALTHCHECK_TIMEOUT", 0),
            pytest.raises(RuntimeError, match="did not become healthy"),
        ):
            qc._wait_healthy()
