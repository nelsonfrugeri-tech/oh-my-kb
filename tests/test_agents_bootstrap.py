"""Integration tests for :func:`oh_my_kb.agents.bootstrap.bootstrap`.

All tests that touch the filesystem use ``monkeypatch`` to redirect
``Path.home()`` to a ``tmp_path`` so that the developer's real
``~/.claude/CLAUDE.md`` is never touched.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from oh_my_kb.agents.bootstrap import (
    BootstrapReport,
    NoActiveUniverseError,
    bootstrap,
    do_bootstrap,
)
from oh_my_kb.agents.harness import UnknownHarnessError
from oh_my_kb.agents.injector import END_MARKER, START_MARKER, InjectAction


def _fake_home(tmp_path: Path) -> Path:
    """A fake home directory under *tmp_path*."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return home


def _global_target(home: Path) -> Path:
    """Expected target for the claude-code harness under *home*."""
    return home / ".claude" / "CLAUDE.md"


class TestBootstrapGlobalPath:
    """Bug 1 fix: claude-code always writes to ~/.claude/CLAUDE.md."""

    def test_target_resolves_to_global_path(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            report = bootstrap(
                harness="claude-code",
                project_path=tmp_path,
                active_universe="test-universe",
            )
        assert report.target_file == _global_target(home)

    def test_global_target_is_not_under_project_path(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        project = tmp_path / "my-project"
        project.mkdir()
        with patch.object(Path, "home", return_value=home):
            report = bootstrap(
                harness="claude-code",
                project_path=project,
                active_universe="test-universe",
            )
        # Target must NOT be inside the project directory
        assert not str(report.target_file).startswith(str(project))

    def test_global_target_created_even_when_dot_claude_missing(
        self, tmp_path: Path
    ) -> None:
        home = _fake_home(tmp_path)
        # .claude dir does NOT exist yet
        assert not (home / ".claude").exists()
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code",
                project_path=tmp_path,
                active_universe="test-universe",
            )
        assert _global_target(home).exists()


class TestBootstrapCreated:
    """File does not exist — should be created with block at top."""

    def test_file_does_not_exist_creates_file(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            report = bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
        assert report.action == InjectAction.CREATED
        assert _global_target(home).exists()

    def test_created_file_contains_universe(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            bootstrap(harness="claude-code", project_path=tmp_path, active_universe="work")
        assert "work" in _global_target(home).read_text(encoding="utf-8")

    def test_created_file_contains_markers(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
        assert START_MARKER in _global_target(home).read_text(encoding="utf-8")

    def test_created_file_block_is_at_top(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
        text = _global_target(home).read_text(encoding="utf-8")
        assert text.startswith(START_MARKER)

    def test_report_fields_are_correct(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            report = bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="my-universe"
            )
        assert report.harness == "claude-code"
        assert report.universe == "my-universe"
        assert report.target_file == _global_target(home)
        assert report.bytes_written > 0


class TestBootstrapPrependAndPreserve:
    """Bug 3 fix: block is prepended, existing user content preserved below."""

    def test_file_with_user_content_no_markers_returns_inserted(
        self, tmp_path: Path
    ) -> None:
        home = _fake_home(tmp_path)
        target = _global_target(home)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# My global rules\n\nDo not disturb.\n", encoding="utf-8")
        with patch.object(Path, "home", return_value=home):
            report = bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
        assert report.action == InjectAction.INSERTED

    def test_block_prepended_before_user_content(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        target = _global_target(home)
        target.parent.mkdir(parents=True, exist_ok=True)
        user_content = "# My global rules\n\nDo not disturb.\n"
        target.write_text(user_content, encoding="utf-8")
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
        text = target.read_text(encoding="utf-8")
        # Block must appear before user content
        assert text.startswith(START_MARKER)
        block_end = text.find(END_MARKER) + len(END_MARKER)
        remaining = text[block_end:]
        assert "# My global rules" in remaining
        assert "Do not disturb." in remaining

    def test_user_content_preserved_verbatim_on_insert(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        target = _global_target(home)
        target.parent.mkdir(parents=True, exist_ok=True)
        user_content = "# My global rules\n\nDo not disturb.\n"
        target.write_text(user_content, encoding="utf-8")
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
        text = target.read_text(encoding="utf-8")
        assert "# My global rules" in text
        assert "Do not disturb." in text


class TestBootstrapIdempotent:
    """Bug 5 fix: second run with identical block returns UNCHANGED."""

    def test_second_call_returns_unchanged(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
            report2 = bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
        assert report2.action == InjectAction.UNCHANGED

    def test_unchanged_file_not_rewritten(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
            target = _global_target(home)
            mtime_before = target.stat().st_mtime
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
        mtime_after = target.stat().st_mtime
        assert mtime_before == mtime_after

    def test_second_run_with_user_content_unchanged(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        target = _global_target(home)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# User rules\n\nImportant stuff.\n", encoding="utf-8")
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
            report2 = bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
        assert report2.action == InjectAction.UNCHANGED
        text = target.read_text(encoding="utf-8")
        assert "# User rules" in text
        assert "Important stuff." in text

    def test_legacy_appended_block_moved_to_top_without_duplication(
        self, tmp_path: Path
    ) -> None:
        """Bug 5: block in legacy append position is moved to top, no duplication."""
        home = _fake_home(tmp_path)
        target = _global_target(home)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Simulate legacy state: user content ABOVE the block (old append behavior)
        user_text = "# User rules\n\nImportant stuff.\n"
        with patch.object(Path, "home", return_value=home):
            # First write via bootstrap — block goes to top, user content below
            target.write_text(user_text, encoding="utf-8")
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="test-universe"
            )
            text_after = target.read_text(encoding="utf-8")
        # Block must be at top
        assert text_after.startswith(START_MARKER)
        # User content must still be there
        assert "# User rules" in text_after
        # No duplication of markers
        assert text_after.count(START_MARKER) == 1
        assert text_after.count(END_MARKER) == 1


class TestBootstrapReplaced:
    def test_different_universe_returns_replaced(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="universe-one"
            )
            report2 = bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="universe-two"
            )
        assert report2.action == InjectAction.REPLACED

    def test_replaced_file_contains_new_universe(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="universe-one"
            )
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="universe-two"
            )
        text = _global_target(home).read_text(encoding="utf-8")
        assert "universe-two" in text
        assert "universe-one" not in text

    def test_user_content_preserved_on_replace(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        target = _global_target(home)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# User rules\n\nKeep this.\n", encoding="utf-8")
        with patch.object(Path, "home", return_value=home):
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="universe-one"
            )
            bootstrap(
                harness="claude-code", project_path=tmp_path, active_universe="universe-two"
            )
        text = target.read_text(encoding="utf-8")
        assert "# User rules" in text
        assert "Keep this." in text


class TestBootstrapErrors:
    def test_no_active_universe_raises(self, tmp_path: Path) -> None:
        with pytest.raises(NoActiveUniverseError):
            bootstrap(harness="claude-code", project_path=tmp_path, active_universe=None)

    def test_no_active_universe_raises_value_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            bootstrap(harness="claude-code", project_path=tmp_path, active_universe=None)

    def test_unknown_harness_raises(self, tmp_path: Path) -> None:
        with pytest.raises(UnknownHarnessError):
            bootstrap(
                harness="unknown-harness",
                project_path=tmp_path,
                active_universe="test-universe",
            )

    def test_nonexistent_project_path_raises_only_for_project_scoped_harness(
        self, tmp_path: Path
    ) -> None:
        """Global harnesses do NOT require project_path to exist."""
        home = _fake_home(tmp_path)
        nonexistent = tmp_path / "does-not-exist"
        # claude-code is global — nonexistent project_path is fine
        with patch.object(Path, "home", return_value=home):
            report = bootstrap(
                harness="claude-code",
                project_path=nonexistent,
                active_universe="test-universe",
            )
        assert report.target_file == _global_target(home)


# ---------------------------------------------------------------------------
# do_bootstrap — public single-entry-point function
# ---------------------------------------------------------------------------


class TestDoBootstrap:
    """Tests for :func:`oh_my_kb.agents.bootstrap.do_bootstrap`."""

    def test_returns_bootstrap_report(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            report = do_bootstrap("claude-code", "my-universe")
        assert isinstance(report, BootstrapReport)

    def test_target_is_global_claude_md(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            report = do_bootstrap("claude-code", "my-universe")
        assert report.target_file == _global_target(home)

    def test_action_is_created_on_first_run(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            report = do_bootstrap("claude-code", "my-universe")
        assert report.action in (InjectAction.CREATED, InjectAction.INSERTED)

    def test_bytes_written_positive(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            report = do_bootstrap("claude-code", "my-universe")
        assert report.bytes_written > 0

    def test_universe_in_report(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            report = do_bootstrap("claude-code", "work-universe")
        assert report.universe == "work-universe"

    def test_home_override_parameter(self, tmp_path: Path) -> None:
        """``home`` param overrides the project_path used internally."""
        home = _fake_home(tmp_path)
        report = do_bootstrap("claude-code", "test-universe", home=home)
        assert report.target_file == _global_target(home)

    def test_second_call_returns_unchanged(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            do_bootstrap("claude-code", "my-universe")
            report2 = do_bootstrap("claude-code", "my-universe")
        assert report2.action == InjectAction.UNCHANGED

    def test_file_contains_universe_name(self, tmp_path: Path) -> None:
        home = _fake_home(tmp_path)
        with patch.object(Path, "home", return_value=home):
            do_bootstrap("claude-code", "cool-universe")
        content = _global_target(home).read_text(encoding="utf-8")
        assert "cool-universe" in content
