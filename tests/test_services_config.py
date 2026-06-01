from pathlib import Path

import pytest

from oh_my_kb.services import DEFAULT_NOTES_ROOT, NOTES_ROOT_ENV, get_notes_root


def test_default_notes_root_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(NOTES_ROOT_ENV, raising=False)
    assert get_notes_root() == DEFAULT_NOTES_ROOT


def test_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(NOTES_ROOT_ENV, str(tmp_path))
    assert get_notes_root() == tmp_path


def test_env_var_expands_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(NOTES_ROOT_ENV, "~/custom-kb")
    assert get_notes_root() == Path.home() / "custom-kb"
