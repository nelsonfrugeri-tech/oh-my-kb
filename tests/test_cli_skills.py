"""Tests for ``omh skills`` CLI commands."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from typer.testing import CliRunner

from oh_my_harness.kb.cli._remote import MANIFEST_URL, RAW_BASE_URL
from oh_my_harness.kb.cli.app import app

_MANIFEST = {
    "schema_version": 1,
    "skills": [
        {
            "name": "python",
            "version": "1.0.0",
            "path": "assets/skills/python",
            "files": [{"path": "SKILL.md", "sha256": "abc123"}],
        },
        {
            "name": "design",
            "version": "1.0.0",
            "path": "assets/skills/design",
            "files": [{"path": "SKILL.md", "sha256": "def456"}],
        },
    ],
    "agents": [],
}

_SKILL_CONTENT = "---\nversion: 1.0.0\n---\n# Python Skill\n"
_SKILL_SHA = hashlib.sha256(_SKILL_CONTENT.encode()).hexdigest()
_MANIFEST_WITH_REAL_SHA = {
    "schema_version": 1,
    "skills": [
        {
            "name": "python",
            "version": "1.0.0",
            "path": "assets/skills/python",
            "files": [{"path": "SKILL.md", "sha256": _SKILL_SHA}],
        }
    ],
    "agents": [],
}


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


class TestSkillsList:
    @respx.mock
    def test_list_shows_skills(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "list"])

        assert result.exit_code == 0, result.output
        assert "python" in result.output
        assert "design" in result.output
        assert "1.0.0" in result.output

    @respx.mock
    def test_list_shows_not_installed(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "list"])

        assert "not-installed" in result.output

    @respx.mock
    def test_list_shows_up_to_date_when_matching(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MANIFEST_WITH_REAL_SHA)
        )
        skill_dir = isolated_home / ".claude" / "skills" / "python"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_SKILL_CONTENT, encoding="utf-8")

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "list"])

        assert "up-to-date" in result.output

    @respx.mock
    def test_list_shows_drift_when_sha_differs(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        skill_dir = isolated_home / ".claude" / "skills" / "python"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("different content", encoding="utf-8")

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "list"])

        assert "drift" in result.output

    @respx.mock
    def test_list_exits_nonzero_on_network_error(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(500, text="error"))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "list"])

        assert result.exit_code != 0


class TestSkillsPull:
    @respx.mock
    def test_pull_single_downloads_files(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        skill_file_url = f"{RAW_BASE_URL}/assets/skills/python/SKILL.md"
        respx.get(skill_file_url).mock(return_value=httpx.Response(200, text=_SKILL_CONTENT))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "pull", "python"])

        assert result.exit_code == 0, result.output
        skill_md = isolated_home / ".claude" / "skills" / "python" / "SKILL.md"
        assert skill_md.exists()
        assert skill_md.read_text() == _SKILL_CONTENT

    @respx.mock
    def test_pull_all_downloads_all_skills(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        for name, path in [("python", "assets/skills/python"), ("design", "assets/skills/design")]:
            url = f"{RAW_BASE_URL}/{path}/SKILL.md"
            respx.get(url).mock(return_value=httpx.Response(200, text=f"# {name}"))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "pull", "--all"])

        assert result.exit_code == 0, result.output
        assert (isolated_home / ".claude" / "skills" / "python" / "SKILL.md").exists()
        assert (isolated_home / ".claude" / "skills" / "design" / "SKILL.md").exists()

    @respx.mock
    def test_pull_unknown_skill_exits_nonzero(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "pull", "nonexistent"])

        assert result.exit_code != 0

    @respx.mock
    def test_pull_without_args_exits_nonzero(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "pull"])

        assert result.exit_code != 0


class TestSkillsDiff:
    @respx.mock
    def test_diff_shows_all_skills(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "diff"])

        assert result.exit_code == 0, result.output
        assert "python" in result.output
        assert "design" in result.output

    @respx.mock
    def test_diff_single_skill(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "diff", "python"])

        assert result.exit_code == 0, result.output
        assert "python" in result.output
        assert "design" not in result.output

    @respx.mock
    def test_diff_unknown_skill_exits_nonzero(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "diff", "nonexistent"])

        assert result.exit_code != 0


class TestSkillsUpdate:
    @respx.mock
    def test_update_pulls_not_installed(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        for name, path in [("python", "assets/skills/python"), ("design", "assets/skills/design")]:
            url = f"{RAW_BASE_URL}/{path}/SKILL.md"
            respx.get(url).mock(return_value=httpx.Response(200, text=f"# {name}"))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "update"])

        assert result.exit_code == 0, result.output
        assert (isolated_home / ".claude" / "skills" / "python" / "SKILL.md").exists()

    @respx.mock
    def test_update_reports_all_up_to_date(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MANIFEST_WITH_REAL_SHA)
        )
        skill_dir = isolated_home / ".claude" / "skills" / "python"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(_SKILL_CONTENT, encoding="utf-8")

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["skills", "update"])

        assert result.exit_code == 0, result.output
        assert "up-to-date" in result.output.lower()
