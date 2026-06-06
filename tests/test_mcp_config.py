from pathlib import Path

import pytest

from oh_my_kb.cli.paths import DATA_ROOT_ENV
from oh_my_kb.mcp.config import (
    DEFAULT_UNIVERSE,
    UNIVERSE_ENV,
    get_active_notes_root,
    get_active_universe,
)


def test_default_universe_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(UNIVERSE_ENV, raising=False)
    assert get_active_universe() == DEFAULT_UNIVERSE


def test_env_overrides_active_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(UNIVERSE_ENV, "research")
    assert get_active_universe() == "research"


def test_notes_root_defaults_to_data_root_plus_slug(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
    monkeypatch.delenv(UNIVERSE_ENV, raising=False)
    # KB_NOTES_ROOT acts as the data root in this server's resolution.
    # When set, it overrides the default per the issue spec.
    assert get_active_notes_root() == tmp_path


def test_notes_root_uses_default_layout_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
    monkeypatch.delenv(UNIVERSE_ENV, raising=False)
    expected = Path.home() / "oh-my-kb" / DEFAULT_UNIVERSE
    assert get_active_notes_root() == expected


def test_explicit_universe_argument_overrides_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(UNIVERSE_ENV, "research")
    monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
    expected = Path.home() / "oh-my-kb" / "personal"
    assert get_active_notes_root(universe="personal") == expected
