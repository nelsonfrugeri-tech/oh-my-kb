"""Integration tests for :func:`oh_my_kb.agents.bootstrap.bootstrap`."""

from __future__ import annotations

from pathlib import Path

import pytest

from oh_my_kb.agents.bootstrap import NoActiveUniverseError, bootstrap
from oh_my_kb.agents.harness import UnknownHarnessError
from oh_my_kb.agents.injector import START_MARKER, InjectAction


class TestBootstrapCreated:
    def test_file_does_not_exist_creates_file(self, tmp_path: Path) -> None:
        report = bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="test-universe"
        )
        assert report.action == InjectAction.CREATED
        target = tmp_path / "CLAUDE.md"
        assert target.exists()

    def test_created_file_contains_universe(self, tmp_path: Path) -> None:
        bootstrap(harness="claude-code", project_path=tmp_path, active_universe="work")
        target = tmp_path / "CLAUDE.md"
        assert "work" in target.read_text(encoding="utf-8")

    def test_created_file_contains_markers(self, tmp_path: Path) -> None:
        bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="test-universe"
        )
        target = tmp_path / "CLAUDE.md"
        assert START_MARKER in target.read_text(encoding="utf-8")

    def test_report_fields_are_correct(self, tmp_path: Path) -> None:
        report = bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="my-universe"
        )
        assert report.harness == "claude-code"
        assert report.universe == "my-universe"
        assert report.target_file == tmp_path / "CLAUDE.md"
        assert report.bytes_written > 0


class TestBootstrapInserted:
    def test_file_with_user_content_no_markers_returns_inserted(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "CLAUDE.md"
        target.write_text("# My project rules\n\nDo not disturb.\n", encoding="utf-8")
        report = bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="test-universe"
        )
        assert report.action == InjectAction.INSERTED

    def test_user_content_preserved_on_insert(self, tmp_path: Path) -> None:
        target = tmp_path / "CLAUDE.md"
        target.write_text("# My project rules\n\nDo not disturb.\n", encoding="utf-8")
        bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="test-universe"
        )
        text = target.read_text(encoding="utf-8")
        assert "# My project rules" in text
        assert "Do not disturb." in text


class TestBootstrapIdempotent:
    def test_second_call_returns_unchanged(self, tmp_path: Path) -> None:
        bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="test-universe"
        )
        report2 = bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="test-universe"
        )
        assert report2.action == InjectAction.UNCHANGED

    def test_unchanged_file_not_rewritten(self, tmp_path: Path) -> None:
        bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="test-universe"
        )
        target = tmp_path / "CLAUDE.md"
        mtime_before = target.stat().st_mtime
        bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="test-universe"
        )
        mtime_after = target.stat().st_mtime
        assert mtime_before == mtime_after


class TestBootstrapReplaced:
    def test_different_universe_returns_replaced(self, tmp_path: Path) -> None:
        bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="universe-one"
        )
        report2 = bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="universe-two"
        )
        assert report2.action == InjectAction.REPLACED

    def test_replaced_file_contains_new_universe(self, tmp_path: Path) -> None:
        bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="universe-one"
        )
        bootstrap(
            harness="claude-code", project_path=tmp_path, active_universe="universe-two"
        )
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "universe-two" in text
        assert "universe-one" not in text


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

    def test_nonexistent_project_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            bootstrap(
                harness="claude-code",
                project_path=tmp_path / "does-not-exist",
                active_universe="test-universe",
            )
