"""Tests for ``omk reindex`` command via Typer's CliRunner.

Drives the real ``app`` object against an isolated config + in-memory Qdrant.
All embedder calls are replaced by a ``StubEmbedder`` via ``ReindexRunner``
injection — no bge-m3 model is loaded.

Pattern mirrors ``tests/test_cli_universe.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _helpers import StubEmbedder, make_note
from typer.testing import CliRunner

from oh_my_harness.kb.cli.app import app
from oh_my_harness.kb.cli.config import CONFIG_DIR_ENV, load_config
from oh_my_harness.kb.cli.paths import DATA_ROOT_ENV
from oh_my_harness.kb.cli.reindex import NoActiveUniverseError, ReindexRunner
from oh_my_harness.kb.core import to_markdown
from oh_my_harness.kb.storage import IN_MEMORY, QdrantStore

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolated config, data root, and in-memory Qdrant."""
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path / "config"))
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path / "data"))
    monkeypatch.setenv("KB_QDRANT_URL", IN_MEMORY)
    return tmp_path


@pytest.fixture
def populated_universe(isolated_env: Path) -> tuple[str, Path]:
    """Create a universe named 'testrun' with one note on disk, return (name, notes_root)."""
    from oh_my_harness.kb.cli.config import add_universe, save_config, set_active

    universe_name = "testrun"
    notes_root = isolated_env / "data" / "testrun"
    notes_root.mkdir(parents=True)

    # Register and activate universe in config.
    cfg = add_universe(load_config(), name=universe_name, notes_root=notes_root)
    cfg = set_active(cfg, universe_name)
    save_config(cfg)

    # Write one note onto disk so reindex has something to upsert.
    note = make_note(title="Hello World", kb_name=universe_name)
    (notes_root / f"{note.slug}.md").write_text(to_markdown(note), encoding="utf-8")

    return universe_name, notes_root


# ---------------------------------------------------------------------------
# ReindexRunner unit tests (not CLI)
# ---------------------------------------------------------------------------


def test_runner_raises_no_active_universe_when_none_configured(
    isolated_env: Path,
) -> None:
    """ReindexRunner.run() raises NoActiveUniverseError when no universe is active."""
    stub = StubEmbedder()
    runner = ReindexRunner(
        store_factory=lambda _url: QdrantStore(IN_MEMORY),
        embedder_factory=lambda: stub,
        qdrant_url_resolver=lambda: IN_MEMORY,
    )
    with pytest.raises(NoActiveUniverseError):
        runner.run()


def test_runner_raises_universe_not_found_when_name_unknown(
    isolated_env: Path,
) -> None:
    """ReindexRunner.run('ghost') raises UniverseNotFoundError."""
    from oh_my_harness.kb.cli.config import UniverseNotFoundError

    stub = StubEmbedder()
    runner = ReindexRunner(
        store_factory=lambda _url: QdrantStore(IN_MEMORY),
        embedder_factory=lambda: stub,
        qdrant_url_resolver=lambda: IN_MEMORY,
    )
    with pytest.raises(UniverseNotFoundError):
        runner.run("ghost")


def test_runner_uses_active_universe_when_no_arg(
    populated_universe: tuple[str, Path],
) -> None:
    """ReindexRunner.run() uses the active universe from config when kb_name=None."""
    _universe_name, _notes_root = populated_universe
    store = QdrantStore(IN_MEMORY)
    stub = StubEmbedder()

    runner = ReindexRunner(
        store_factory=lambda _url: store,
        embedder_factory=lambda: stub,
        qdrant_url_resolver=lambda: IN_MEMORY,
    )
    report = runner.run()

    assert report.scanned == 1
    assert report.upserted == 1
    assert report.removed == 0


def test_runner_uses_explicit_universe_arg(
    isolated_env: Path,
) -> None:
    """ReindexRunner.run('alt') uses the specified universe, not the active one."""
    from oh_my_harness.kb.cli.config import add_universe, save_config, set_active

    # Create 'default' as active and 'alt' as an alternative.
    alt_root = isolated_env / "data" / "alt"
    alt_root.mkdir(parents=True)

    cfg = add_universe(load_config(), name="default", notes_root=isolated_env / "data" / "default")
    cfg = add_universe(cfg, name="alt", notes_root=alt_root)
    cfg = set_active(cfg, "default")
    save_config(cfg)

    # Write a note into 'alt's notes_root.
    note = make_note(title="Alt Note", kb_name="alt")
    (alt_root / f"{note.slug}.md").write_text(to_markdown(note), encoding="utf-8")

    store = QdrantStore(IN_MEMORY)
    stub = StubEmbedder()

    runner = ReindexRunner(
        store_factory=lambda _url: store,
        embedder_factory=lambda: stub,
        qdrant_url_resolver=lambda: IN_MEMORY,
    )
    report = runner.run("alt")

    assert report.scanned == 1
    assert report.upserted == 1


# ---------------------------------------------------------------------------
# CLI integration tests via CliRunner
# ---------------------------------------------------------------------------


def _make_stub_runner_factory(tmp_notes_root: Path) -> ReindexRunner:
    """Helper: build a ReindexRunner with StubEmbedder and in-memory store."""
    store = QdrantStore(IN_MEMORY)
    stub = StubEmbedder()
    return ReindexRunner(
        store_factory=lambda _url: store,
        embedder_factory=lambda: stub,
        qdrant_url_resolver=lambda: IN_MEMORY,
    )


def test_cli_reindex_uses_active_universe(
    runner: CliRunner,
    populated_universe: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``omk reindex`` succeeds and prints scanned/upserted/removed when active universe set."""
    _universe_name, _notes_root = populated_universe

    # Patch ReindexRunner inside app.py to avoid loading the real bge-m3 embedder.
    store = QdrantStore(IN_MEMORY)
    stub = StubEmbedder()
    fake_runner = ReindexRunner(
        store_factory=lambda _url: store,
        embedder_factory=lambda: stub,
        qdrant_url_resolver=lambda: IN_MEMORY,
    )
    monkeypatch.setattr("oh_my_harness.kb.cli.reindex.ReindexRunner", lambda **_kw: fake_runner)

    result = runner.invoke(app, ["reindex"])

    assert result.exit_code == 0, result.output
    assert "scanned" in result.output
    assert "upserted" in result.output
    assert "removed" in result.output


def test_cli_reindex_with_explicit_universe_flag(
    runner: CliRunner,
    populated_universe: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``omk reindex --universe testrun`` succeeds."""
    universe_name_val, _notes_root = populated_universe

    store = QdrantStore(IN_MEMORY)
    stub = StubEmbedder()
    fake_runner = ReindexRunner(
        store_factory=lambda _url: store,
        embedder_factory=lambda: stub,
        qdrant_url_resolver=lambda: IN_MEMORY,
    )
    monkeypatch.setattr("oh_my_harness.kb.cli.reindex.ReindexRunner", lambda **_kw: fake_runner)

    result = runner.invoke(app, ["reindex", "--universe", universe_name_val])

    assert result.exit_code == 0, result.output
    assert "scanned" in result.output


def test_cli_reindex_exit_1_when_no_active_universe(
    runner: CliRunner,
    isolated_env: Path,
) -> None:
    """``omk reindex`` exits 1 when no universe is configured."""
    result = runner.invoke(app, ["reindex"])
    assert result.exit_code == 1


def test_cli_reindex_exit_1_when_universe_unknown(
    runner: CliRunner,
    populated_universe: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``omk reindex --universe ghost`` exits 1."""
    result = runner.invoke(app, ["reindex", "--universe", "ghost"])
    assert result.exit_code == 1
