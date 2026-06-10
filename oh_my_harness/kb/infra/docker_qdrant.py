"""Qdrant container lifecycle management via the Docker Python SDK.

Manages a single ``oh-my-harness-qdrant`` container: pull image, create,
start, stop, and health-check.  All Docker interactions go through
the injected :class:`docker.DockerClient` so tests can supply a
:class:`unittest.mock.MagicMock` without a real Docker daemon.

Typical usage::

    qc = QdrantContainer(name="oh-my-harness-qdrant", image="qdrant/qdrant:latest", port=6333)
    qc.ensure_image()   # pulls if not cached
    qc.ensure_running() # starts (or confirms already running)

    qc.status()  # ContainerStatus(running=True, ...)
    qc.stop()    # graceful stop; returns False if already stopped
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docker import DockerClient


class DockerNotRunningError(RuntimeError):
    """Raised when the Docker daemon is not reachable.

    Common causes:
    - Docker Desktop is not started.
    - The Docker daemon is not running.
    - The current user is not in the ``docker`` group (Linux without rootless).

    Resolution:
    - macOS/Windows: start Docker Desktop.
    - Linux: ``sudo systemctl start docker`` or ``sudo usermod -aG docker $USER``
      (then log out and back in).
    """


class ImageAction(StrEnum):
    PULLED = "pulled"
    CACHED = "cached"


class ContainerAction(StrEnum):
    STARTED = "started"
    ALREADY_RUNNING = "already_running"
    CREATED = "created"


@dataclass(frozen=True, slots=True)
class ContainerStatus:
    running: bool
    image: str
    port: int
    container_id: str | None


HEALTHCHECK_TIMEOUT = 60  # seconds
HEALTHCHECK_INTERVAL = 1  # seconds


class QdrantContainer:
    """Manage the lifecycle of a Qdrant Docker container.

    Args:
        name: Docker container name (e.g. ``"oh-my-harness-qdrant"``).
        image: Docker image to use (e.g. ``"qdrant/qdrant:latest"``).
        port: Host port to bind to container port 6333.
        client: Injected :class:`docker.DockerClient`.  If ``None``,
            :func:`docker.from_env` is called lazily on first use.
    """

    def __init__(
        self,
        name: str,
        image: str,
        port: int,
        client: DockerClient | None = None,
    ) -> None:
        self._name = name
        self._image = image
        self._port = port
        self._client = client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _docker(self) -> DockerClient:
        """Return the Docker client, creating it from the environment if needed."""
        if self._client is not None:
            return self._client
        try:
            import docker

            self._client = docker.from_env()
            return self._client
        except Exception as exc:
            raise DockerNotRunningError(
                "Docker isn't running — start Docker Desktop or the Docker daemon.\n"
                "  macOS/Windows: open Docker Desktop.\n"
                "  Linux: run `sudo systemctl start docker` or add your user to the "
                "`docker` group with `sudo usermod -aG docker $USER` then log out and in."
            ) from exc

    def _get_container(self) -> Any | None:
        """Return the container object if it exists, otherwise ``None``."""
        try:

            return self._docker().containers.get(self._name)
        except Exception:
            # docker.errors.NotFound and any other errors → container absent
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_image(self) -> ImageAction:
        """Pull the image if it is not already in the local cache.

        Returns:
            :attr:`ImageAction.CACHED` if the image already exists locally;
            :attr:`ImageAction.PULLED` if it was downloaded.

        Raises:
            DockerNotRunningError: if Docker is not reachable.
        """
        client = self._docker()
        try:

            client.images.get(self._image)
            return ImageAction.CACHED
        except Exception:
            pass
        # Image not found locally — pull it (may take a while for first download)
        client.images.pull(self._image)
        return ImageAction.PULLED

    def ensure_running(self) -> ContainerAction:
        """Ensure the container is running.

        If the container does not exist it is created and started.
        If it exists but is stopped it is restarted.
        If it is already running this is a no-op.

        After starting the container the method polls the Qdrant health
        endpoint for up to :data:`HEALTHCHECK_TIMEOUT` seconds.

        Returns:
            :class:`ContainerAction` describing what happened.

        Raises:
            DockerNotRunningError: if Docker is not reachable.
            RuntimeError: if Qdrant does not become healthy within the timeout.
        """
        container = self._get_container()

        if container is not None:
            # Reload to get current status
            container.reload()
            if container.status == "running":
                return ContainerAction.ALREADY_RUNNING

            # Container exists but is stopped — restart it
            container.start()
            self._wait_healthy()
            return ContainerAction.STARTED

        # Container does not exist — create and start it
        client = self._docker()
        client.containers.run(
            self._image,
            name=self._name,
            ports={"6333/tcp": self._port},
            detach=True,
        )
        self._wait_healthy()
        return ContainerAction.CREATED

    def stop(self) -> bool:
        """Stop the container gracefully.

        Returns:
            ``True`` if the container was stopped; ``False`` if it was
            already stopped or did not exist.
        """
        container = self._get_container()
        if container is None:
            return False
        container.reload()
        if container.status != "running":
            return False
        container.stop()
        return True

    def status(self) -> ContainerStatus:
        """Return the current status of the container.

        Returns a :class:`ContainerStatus` with ``running=False`` and
        empty fields when the container does not exist.
        """
        container = self._get_container()
        if container is None:
            return ContainerStatus(
                running=False,
                image=self._image,
                port=self._port,
                container_id=None,
            )
        container.reload()
        return ContainerStatus(
            running=container.status == "running",
            image=self._image,
            port=self._port,
            container_id=container.short_id,
        )

    # ------------------------------------------------------------------
    # Health check (reuses QdrantStore to avoid a new HTTP dependency)
    # ------------------------------------------------------------------

    def _wait_healthy(self) -> None:
        """Poll Qdrant health endpoint until it responds or timeout expires.

        Raises:
            RuntimeError: if Qdrant does not respond within
                :data:`HEALTHCHECK_TIMEOUT` seconds.
        """
        from oh_my_harness.kb.storage import QdrantStore

        url = f"http://localhost:{self._port}"
        store = QdrantStore(url)
        deadline = time.monotonic() + HEALTHCHECK_TIMEOUT
        while time.monotonic() < deadline:
            if store.healthcheck():
                return
            time.sleep(HEALTHCHECK_INTERVAL)
        raise RuntimeError(
            f"Qdrant at {url} did not become healthy within {HEALTHCHECK_TIMEOUT}s"
        )
