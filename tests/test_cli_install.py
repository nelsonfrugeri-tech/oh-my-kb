"""Tests for the Installer orchestrator using fully injected fakes.

No Docker, no HuggingFace download. We assert step ordering, idempotency,
the healthcheck retry loop, and the failure path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from oh_my_kb.cli.config import (
    CONFIG_DIR_ENV,
    collection_name_for,
    config_path,
    load_config,
)
from oh_my_kb.cli.installer import (
    DEFAULT_UNIVERSE,
    Installer,
    QdrantUnreachableError,
)
from oh_my_kb.cli.paths import DATA_ROOT_ENV
from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.storage import DENSE_DIM, IN_MEMORY, QdrantStore


class _FakeEmbedder(Embedder):
    @property
    def dense_dim(self) -> int:
        return DENSE_DIM

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        return [
            EmbeddingResult(
                dense=[0.0] * DENSE_DIM,
                sparse=SparseVector(indices=[1], values=[1.0]),
            )
            for _ in texts
        ]


@dataclass
class _FakeStore:
    """Wraps an in-memory :class:`QdrantStore` but lets the test pretend
    Qdrant is initially down by gating ``healthcheck`` behind a counter."""

    _real: QdrantStore = field(default_factory=lambda: QdrantStore(IN_MEMORY))
    unhealthy_calls: int = 0
    healthcheck_calls: int = 0

    def healthcheck(self) -> bool:
        self.healthcheck_calls += 1
        if self.unhealthy_calls > 0:
            self.unhealthy_calls -= 1
            return False
        return True

    def ensure_collection(self, name: str) -> None:
        self._real.ensure_collection(name)

    def collection_exists(self, name: str) -> bool:
        return self._real.collection_exists(name)


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path / "config"))
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path / "data"))
    return tmp_path


def _make_installer(
    *,
    store: _FakeStore,
    docker_calls: list[list[str]],
    sleep_calls: list[float],
    embedder_calls: list[int],
) -> Installer:
    def fake_docker(argv: list[str]) -> None:
        docker_calls.append(argv)

    def fake_sleeper(seconds: float) -> None:
        sleep_calls.append(seconds)

    def fake_embedder_factory() -> Embedder:
        embedder_calls.append(1)
        return _FakeEmbedder()

    def fake_store_factory(_url: str) -> QdrantStore:
        return store  # type: ignore[return-value]

    return Installer(
        qdrant_url="http://fake:6333",
        docker_runner=fake_docker,
        store_factory=fake_store_factory,
        embedder_factory=fake_embedder_factory,
        sleeper=fake_sleeper,
        healthcheck_timeout=5.0,
        healthcheck_interval=0.1,
    )


def test_install_happy_path_qdrant_already_healthy(isolated_env: Path) -> None:
    store = _FakeStore()
    docker, sleeps, embedder = [], [], []
    installer = _make_installer(
        store=store, docker_calls=docker, sleep_calls=sleeps, embedder_calls=embedder
    )

    report = installer.run()

    # Qdrant was healthy from the start: docker compose was not invoked.
    assert docker == []
    # Embedder was loaded exactly once.
    assert embedder == [1]
    # Universe + collection + config all in place.
    assert report.universe == DEFAULT_UNIVERSE
    assert report.collection == collection_name_for(DEFAULT_UNIVERSE)
    assert store.collection_exists(report.collection)
    assert report.notes_root.is_dir()
    assert config_path().is_file()
    cfg = load_config()
    assert cfg.active == DEFAULT_UNIVERSE
    assert cfg.has(DEFAULT_UNIVERSE)


def test_install_starts_qdrant_when_down_and_waits_for_health(isolated_env: Path) -> None:
    # Pretend Qdrant is unhealthy for two checks, then comes up.
    store = _FakeStore(unhealthy_calls=2)
    docker, sleeps, embedder = [], [], []
    installer = _make_installer(
        store=store, docker_calls=docker, sleep_calls=sleeps, embedder_calls=embedder
    )

    report = installer.run()

    assert len(docker) == 1, "docker compose up -d must be invoked once"
    assert docker[0][:2] == ["docker", "compose"]
    assert sleeps, "sleeper must be called while waiting for the healthcheck"
    assert all(s == installer.healthcheck_interval for s in sleeps)
    assert report.qdrant_url == "http://fake:6333"


def test_install_is_idempotent(isolated_env: Path) -> None:
    store = _FakeStore()
    docker, sleeps, embedder = [], [], []
    installer = _make_installer(
        store=store, docker_calls=docker, sleep_calls=sleeps, embedder_calls=embedder
    )

    installer.run()
    second_report = installer.run()

    # Single config file, single universe entry.
    cfg = load_config()
    assert len(cfg.universes) == 1
    assert cfg.active == DEFAULT_UNIVERSE
    # Second run reports that the universe and collection already exist.
    actions = " | ".join(second_report.actions)
    assert "already in config" in actions
    assert "already exists" in actions
    assert "already active" in actions


def test_install_raises_when_qdrant_never_becomes_healthy(isolated_env: Path) -> None:
    import time as _time

    store = _FakeStore(unhealthy_calls=9999)
    docker_calls: list[list[str]] = []

    def fake_docker(argv: list[str]) -> None:
        docker_calls.append(argv)

    installer = Installer(
        qdrant_url="http://fake:6333",
        docker_runner=fake_docker,
        store_factory=lambda _url: store,  # type: ignore[return-value,arg-type]
        embedder_factory=_FakeEmbedder,
        sleeper=lambda _s: _time.sleep(0.01),
        healthcheck_timeout=0.1,
        healthcheck_interval=0.01,
    )

    with pytest.raises(QdrantUnreachableError):
        installer.run()
