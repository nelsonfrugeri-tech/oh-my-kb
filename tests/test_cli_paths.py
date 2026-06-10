from pathlib import Path

import pytest

from oh_my_harness.kb.cli.paths import (
    DATA_ROOT_ENV,
    DEFAULT_DATA_ROOT,
    default_notes_root_for,
    get_data_root,
)


def test_default_data_root_is_visible_oh_my_kb_dir() -> None:
    assert Path.home() / "oh-my-harness" == DEFAULT_DATA_ROOT
    assert not DEFAULT_DATA_ROOT.name.startswith(".")


def test_get_data_root_uses_env_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
    assert get_data_root() == tmp_path


def test_get_data_root_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
    assert get_data_root() == DEFAULT_DATA_ROOT


def test_default_notes_root_for_appends_slug(tmp_path: Path) -> None:
    assert default_notes_root_for("Pessoal & Família", data_root=tmp_path) == (
        tmp_path / "pessoal-familia"
    )


def test_default_notes_root_for_uses_data_root_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
    assert default_notes_root_for("default") == tmp_path / "default"
