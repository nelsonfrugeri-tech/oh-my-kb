from pathlib import Path

import pytest

from oh_my_kb.cli.config import (
    CONFIG_DIR_ENV,
    CONFIG_FILE_NAME,
    CLIConfig,
    UniverseAlreadyExistsError,
    UniverseNotFoundError,
    add_universe,
    config_path,
    load_config,
    save_config,
    set_active,
)


@pytest.fixture
def config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect ~/.config/oh-my-kb to a tmp dir for the test."""
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path))
    return tmp_path


def test_config_path_honors_env(config_dir: Path) -> None:
    assert config_path() == config_dir / CONFIG_FILE_NAME


def test_load_config_returns_empty_when_missing(config_dir: Path) -> None:
    cfg = load_config()
    assert cfg == CLIConfig()
    assert cfg.universes == []
    assert cfg.active is None


def test_save_then_load_round_trip(config_dir: Path, tmp_path: Path) -> None:
    notes_root = tmp_path / "oh-my-kb" / "default"
    base = CLIConfig()
    base = add_universe(base, name="default", notes_root=notes_root)
    base = set_active(base, "default")
    written_path = save_config(base)

    assert written_path == config_path()
    assert written_path.is_file()

    restored = load_config()
    assert restored.active == "default"
    assert len(restored.universes) == 1
    assert restored.universes[0].name == "default"
    assert restored.universes[0].notes_root == notes_root
    assert restored.universes[0].collection == "kb_default"


def test_add_universe_appends_and_sets_collection(config_dir: Path, tmp_path: Path) -> None:
    cfg = add_universe(CLIConfig(), name="engineering", notes_root=tmp_path)
    assert cfg.universes[0].collection == "kb_engineering"
    assert cfg.has("engineering")


def test_add_universe_rejects_duplicate(config_dir: Path, tmp_path: Path) -> None:
    cfg = add_universe(CLIConfig(), name="default", notes_root=tmp_path)
    with pytest.raises(UniverseAlreadyExistsError):
        add_universe(cfg, name="default", notes_root=tmp_path)


def test_set_active_changes_active_field(config_dir: Path, tmp_path: Path) -> None:
    cfg = add_universe(CLIConfig(), name="default", notes_root=tmp_path)
    cfg = set_active(cfg, "default")
    assert cfg.active == "default"


def test_set_active_unknown_universe_raises(config_dir: Path) -> None:
    with pytest.raises(UniverseNotFoundError):
        set_active(CLIConfig(), "nope")


def test_save_creates_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir"
    monkeypatch.setenv(CONFIG_DIR_ENV, str(target))
    cfg = add_universe(CLIConfig(), name="default", notes_root=tmp_path)

    written = save_config(cfg)

    assert target.is_dir()
    assert written.is_file()
