"""Tests for :mod:`oh_my_harness.kb.agents.hooks`.

Coverage:
- Empty settings.json → hook is added
- Existing settings.json with unrelated hooks → hook added without disturbing them
- Idempotent: running install twice does not duplicate
- Non-claude-code harness → hook is NOT added
- settings.json invalid JSON → fails clearly (not silently corrupts)
- settings.json missing → treated as {}
- Uninstall: hook removed; uninstall when absent is a no-op
- Pure mutation helpers (_mutate_install, _mutate_uninstall, _find_omh_hook_index)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from oh_my_harness.kb.agents.hooks import (
    _OMH_HOOK_PREFIX,
    UnsupportedHarnessError,
    _build_omh_hook_entry,
    _find_omh_hook_index,
    _load_settings,
    _mutate_install,
    _mutate_uninstall,
    _write_settings_atomic,
    install_session_start,
    settings_path_for,
    uninstall_session_start,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# settings_path_for
# ---------------------------------------------------------------------------


class TestSettingsPathFor:
    def test_claude_code_returns_dot_claude_settings(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        with patch.object(Path, "home", return_value=tmp_path):
            path = settings_path_for("claude-code")
        assert path == tmp_path / ".claude" / "settings.json"

    def test_unsupported_harness_raises(self) -> None:
        with pytest.raises(UnsupportedHarnessError, match="does not support"):
            settings_path_for("cursor")

    def test_unsupported_harness_unknown_raises(self) -> None:
        with pytest.raises(UnsupportedHarnessError):
            settings_path_for("some-unknown-harness")


# ---------------------------------------------------------------------------
# _load_settings
# ---------------------------------------------------------------------------


class TestLoadSettings:
    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        result = _load_settings(tmp_path / "nonexistent.json")
        assert result == {}

    def test_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("", encoding="utf-8")
        result = _load_settings(path)
        assert result == {}

    def test_whitespace_only_returns_empty_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("   \n", encoding="utf-8")
        result = _load_settings(path)
        assert result == {}

    def test_valid_json_returned(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        _write_json(path, {"foo": "bar"})
        result = _load_settings(path)
        assert result == {"foo": "bar"}

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("{this is not valid json}", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            _load_settings(path)


# ---------------------------------------------------------------------------
# Pure mutation helpers
# ---------------------------------------------------------------------------


class TestMutateInstall:
    def test_empty_settings_adds_hook(self) -> None:
        settings: dict = {}
        updated, action = _mutate_install(settings)
        assert action == "installed"
        hooks_list = updated["hooks"]["SessionStart"]
        assert len(hooks_list) == 1
        assert _OMH_HOOK_PREFIX in hooks_list[0]["hooks"][0]["command"]

    def test_existing_unrelated_hooks_preserved(self) -> None:
        settings: dict = {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "my-project",
                        "hooks": [{"type": "command", "command": "echo hello"}],
                    }
                ]
            }
        }
        updated, action = _mutate_install(settings)
        assert action == "installed"
        hooks_list = updated["hooks"]["SessionStart"]
        # Original unrelated hook is still present
        commands = [h["command"] for entry in hooks_list for h in entry["hooks"]]
        assert "echo hello" in commands
        # Our hook is also present
        assert any(_OMH_HOOK_PREFIX in cmd for cmd in commands)

    def test_idempotent_does_not_duplicate(self) -> None:
        settings: dict = {}
        updated, _ = _mutate_install(settings)
        updated2, action2 = _mutate_install(updated)
        hooks_list = updated2["hooks"]["SessionStart"]
        # Count how many entries have our prefix
        our_count = sum(
            1
            for entry in hooks_list
            for h in entry["hooks"]
            if isinstance(h.get("command"), str) and _OMH_HOOK_PREFIX in h["command"]
        )
        assert our_count == 1, "hook must not be duplicated"
        assert action2 == "already_present"

    def test_mutated_hook_already_present_returns_already_present(self) -> None:
        entry = _build_omh_hook_entry()
        settings: dict = {"hooks": {"SessionStart": [entry]}}
        _, action = _mutate_install(settings)
        assert action == "already_present"

    def test_other_hook_sections_preserved(self) -> None:
        settings: dict = {
            "hooks": {
                "PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "ls"}]}]
            }
        }
        updated, _ = _mutate_install(settings)
        assert "PreToolUse" in updated["hooks"]
        assert updated["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "ls"


class TestMutateUninstall:
    def test_removes_existing_hook(self) -> None:
        settings: dict = {}
        installed, _ = _mutate_install(settings)
        uninstalled, was_removed = _mutate_uninstall(installed)
        assert was_removed is True
        assert "hooks" not in uninstalled

    def test_no_hook_present_returns_not_removed(self) -> None:
        settings: dict = {"foo": "bar"}
        _, was_removed = _mutate_uninstall(settings)
        assert was_removed is False

    def test_unrelated_hooks_preserved_after_uninstall(self) -> None:
        settings: dict = {
            "hooks": {
                "SessionStart": [
                    {"matcher": "other", "hooks": [{"type": "command", "command": "echo x"}]},
                ]
            }
        }
        installed, _ = _mutate_install(settings)
        uninstalled, was_removed = _mutate_uninstall(installed)
        assert was_removed is True
        # The unrelated hook should still be there
        remaining = uninstalled["hooks"]["SessionStart"]
        assert len(remaining) == 1
        assert remaining[0]["hooks"][0]["command"] == "echo x"

    def test_empty_session_start_cleaned_up(self) -> None:
        entry = _build_omh_hook_entry()
        settings: dict = {"hooks": {"SessionStart": [entry]}}
        uninstalled, was_removed = _mutate_uninstall(settings)
        assert was_removed is True
        # SessionStart list is empty → section should be cleaned up
        assert "SessionStart" not in uninstalled.get("hooks", {})


class TestFindOmhHookIndex:
    def test_empty_list_returns_minus_one(self) -> None:
        assert _find_omh_hook_index([]) == -1

    def test_finds_our_hook(self) -> None:
        hooks_list = [_build_omh_hook_entry()]
        # Our hook contains the sentinel prefix inside the command string
        assert _find_omh_hook_index(hooks_list) == 0

    def test_unrelated_hook_returns_minus_one(self) -> None:
        hooks_list = [{"matcher": "", "hooks": [{"type": "command", "command": "echo hi"}]}]
        assert _find_omh_hook_index(hooks_list) == -1

    def test_finds_second_entry(self) -> None:
        other = {"matcher": "", "hooks": [{"type": "command", "command": "echo x"}]}
        ours = _build_omh_hook_entry()
        hooks_list = [other, ours]
        assert _find_omh_hook_index(hooks_list) == 1


# ---------------------------------------------------------------------------
# _write_settings_atomic
# ---------------------------------------------------------------------------


class TestWriteSettingsAtomic:
    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "settings.json"
        _write_settings_atomic(path, {"key": "value"})
        assert path.exists()
        data = json.loads(path.read_text())
        assert data == {"key": "value"}

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        _write_settings_atomic(path, {"old": True})
        _write_settings_atomic(path, {"new": True})
        data = json.loads(path.read_text())
        assert data == {"new": True}
        assert "old" not in data

    def test_output_is_valid_json_with_newline(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        _write_settings_atomic(path, {"a": 1})
        content = path.read_text(encoding="utf-8")
        assert content.endswith("\n")
        json.loads(content)  # must not raise


# ---------------------------------------------------------------------------
# install_session_start — integration (uses tmp HOME)
# ---------------------------------------------------------------------------


class TestInstallSessionStart:
    def test_empty_settings_gets_hook_installed(self, tmp_path: Path) -> None:
        report = install_session_start("claude-code", home=tmp_path)
        assert report.action == "installed"
        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        data = _read_json(settings_path)
        commands = [
            h["command"]
            for entry in data["hooks"]["SessionStart"]
            for h in entry["hooks"]
        ]
        assert any(_OMH_HOOK_PREFIX in cmd for cmd in commands)

    def test_idempotent_second_install_returns_already_present(self, tmp_path: Path) -> None:
        install_session_start("claude-code", home=tmp_path)
        report2 = install_session_start("claude-code", home=tmp_path)
        assert report2.action == "already_present"

    def test_idempotent_does_not_duplicate_hook(self, tmp_path: Path) -> None:
        install_session_start("claude-code", home=tmp_path)
        install_session_start("claude-code", home=tmp_path)
        settings_path = tmp_path / ".claude" / "settings.json"
        data = _read_json(settings_path)
        our_hooks = [
            h
            for entry in data["hooks"]["SessionStart"]
            for h in entry["hooks"]
            if isinstance(h.get("command"), str) and _OMH_HOOK_PREFIX in h["command"]
        ]
        assert len(our_hooks) == 1

    def test_existing_settings_with_unrelated_hooks_preserved(self, tmp_path: Path) -> None:
        settings_path = tmp_path / ".claude" / "settings.json"
        existing = {
            "permissions": {"allow": ["Read"]},
            "hooks": {
                "PreToolUse": [
                    {"matcher": "", "hooks": [{"type": "command", "command": "echo pre"}]}
                ]
            },
        }
        _write_json(settings_path, existing)

        install_session_start("claude-code", home=tmp_path)

        data = _read_json(settings_path)
        # Original permissions preserved
        assert data["permissions"]["allow"] == ["Read"]
        # Original PreToolUse hook preserved
        assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo pre"
        # Our hook added
        session_start_commands = [
            h["command"]
            for entry in data["hooks"]["SessionStart"]
            for h in entry["hooks"]
        ]
        assert any(_OMH_HOOK_PREFIX in cmd for cmd in session_start_commands)

    def test_non_claude_code_harness_returns_skipped(self, tmp_path: Path) -> None:
        report = install_session_start("cursor", home=tmp_path)
        assert report.action == "skipped"
        assert "cursor" in (report.reason or "")
        # No file should be created
        assert not (tmp_path / ".claude" / "settings.json").exists()

    def test_unsupported_unknown_harness_returns_skipped(self, tmp_path: Path) -> None:
        report = install_session_start("some-unknown-harness", home=tmp_path)
        assert report.action == "skipped"

    def test_invalid_json_raises_clearly(self, tmp_path: Path) -> None:
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text("{invalid json}", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            install_session_start("claude-code", home=tmp_path)

    def test_report_contains_correct_settings_path(self, tmp_path: Path) -> None:
        report = install_session_start("claude-code", home=tmp_path)
        assert report.settings_path == tmp_path / ".claude" / "settings.json"

    def test_hook_command_contains_drink_context(self, tmp_path: Path) -> None:
        install_session_start("claude-code", home=tmp_path)
        settings_path = tmp_path / ".claude" / "settings.json"
        data = _read_json(settings_path)
        commands = [
            h["command"]
            for entry in data["hooks"]["SessionStart"]
            for h in entry["hooks"]
        ]
        assert any("drink_context" in cmd for cmd in commands)

    def test_missing_settings_directory_is_created(self, tmp_path: Path) -> None:
        # .claude directory does not exist yet
        assert not (tmp_path / ".claude").exists()
        install_session_start("claude-code", home=tmp_path)
        assert (tmp_path / ".claude" / "settings.json").exists()


# ---------------------------------------------------------------------------
# uninstall_session_start — integration
# ---------------------------------------------------------------------------


class TestUninstallSessionStart:
    def test_removes_installed_hook(self, tmp_path: Path) -> None:
        install_session_start("claude-code", home=tmp_path)
        report = uninstall_session_start("claude-code", home=tmp_path)
        assert report.action == "removed"

        settings_path = tmp_path / ".claude" / "settings.json"
        data = _read_json(settings_path)
        # hooks section may be absent entirely or SessionStart may be absent/empty
        hooks = data.get("hooks", {})
        session_start = hooks.get("SessionStart", [])
        our_hooks = [
            h
            for entry in session_start
            for h in entry["hooks"]
            if isinstance(h.get("command"), str) and _OMH_HOOK_PREFIX in h["command"]
        ]
        assert our_hooks == []

    def test_uninstall_when_not_present_returns_skipped(self, tmp_path: Path) -> None:
        settings_path = tmp_path / ".claude" / "settings.json"
        _write_json(settings_path, {"permissions": {}})
        report = uninstall_session_start("claude-code", home=tmp_path)
        assert report.action == "skipped"

    def test_uninstall_unsupported_harness_returns_skipped(self, tmp_path: Path) -> None:
        report = uninstall_session_start("cursor", home=tmp_path)
        assert report.action == "skipped"

    def test_uninstall_idempotent(self, tmp_path: Path) -> None:
        install_session_start("claude-code", home=tmp_path)
        uninstall_session_start("claude-code", home=tmp_path)
        report2 = uninstall_session_start("claude-code", home=tmp_path)
        assert report2.action == "skipped"
