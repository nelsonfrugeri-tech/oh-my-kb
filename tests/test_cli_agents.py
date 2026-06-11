"""Tests for ``omh agents`` CLI commands."""

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

_AGENT_CONTENT = "---\nversion: 1.0.0\n---\n# Developer Agent\n"
_AGENT_SHA = hashlib.sha256(_AGENT_CONTENT.encode()).hexdigest()

_MANIFEST = {
    "schema_version": 1,
    "skills": [],
    "agents": [
        {
            "name": "developer",
            "version": "1.0.0",
            "path": "assets/agents/developer.md",
            "sha256": "abc123",
        },
        {
            "name": "qa",
            "version": "1.0.0",
            "path": "assets/agents/qa.md",
            "sha256": "def456",
        },
    ],
}

_MANIFEST_WITH_REAL_SHA = {
    "schema_version": 1,
    "skills": [],
    "agents": [
        {
            "name": "developer",
            "version": "1.0.0",
            "path": "assets/agents/developer.md",
            "sha256": _AGENT_SHA,
        }
    ],
}


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


class TestAgentsList:
    @respx.mock
    def test_list_shows_agents(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "list"])

        assert result.exit_code == 0, result.output
        assert "developer" in result.output
        assert "qa" in result.output
        assert "1.0.0" in result.output

    @respx.mock
    def test_list_shows_not_installed(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "list"])

        assert "not-installed" in result.output

    @respx.mock
    def test_list_shows_up_to_date_when_matching(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MANIFEST_WITH_REAL_SHA)
        )
        agents_dir = isolated_home / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "developer.md").write_text(_AGENT_CONTENT, encoding="utf-8")

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "list"])

        assert "up-to-date" in result.output

    @respx.mock
    def test_list_exits_nonzero_on_network_error(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(500, text="error"))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "list"])

        assert result.exit_code != 0


class TestAgentsPull:
    @respx.mock
    def test_pull_single_downloads_file(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        agent_url = f"{RAW_BASE_URL}/assets/agents/developer.md"
        respx.get(agent_url).mock(return_value=httpx.Response(200, text=_AGENT_CONTENT))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "pull", "developer"])

        assert result.exit_code == 0, result.output
        agent_md = isolated_home / ".claude" / "agents" / "developer.md"
        assert agent_md.exists()
        assert agent_md.read_text() == _AGENT_CONTENT

    @respx.mock
    def test_pull_all_downloads_all_agents(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        for name in ["developer", "qa"]:
            url = f"{RAW_BASE_URL}/assets/agents/{name}.md"
            respx.get(url).mock(return_value=httpx.Response(200, text=f"# {name}"))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "pull", "--all"])

        assert result.exit_code == 0, result.output
        assert (isolated_home / ".claude" / "agents" / "developer.md").exists()
        assert (isolated_home / ".claude" / "agents" / "qa.md").exists()

    @respx.mock
    def test_pull_unknown_agent_exits_nonzero(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "pull", "nonexistent"])

        assert result.exit_code != 0

    @respx.mock
    def test_pull_without_args_exits_nonzero(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "pull"])

        assert result.exit_code != 0


class TestAgentsDiff:
    @respx.mock
    def test_diff_shows_all_agents(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "diff"])

        assert result.exit_code == 0, result.output
        assert "developer" in result.output
        assert "qa" in result.output

    @respx.mock
    def test_diff_single_agent(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "diff", "developer"])

        assert result.exit_code == 0, result.output
        assert "developer" in result.output
        assert "qa" not in result.output


class TestAgentsUpdate:
    @respx.mock
    def test_update_pulls_not_installed(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        for name in ["developer", "qa"]:
            url = f"{RAW_BASE_URL}/assets/agents/{name}.md"
            respx.get(url).mock(return_value=httpx.Response(200, text=f"# {name}"))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "update"])

        assert result.exit_code == 0, result.output
        assert (isolated_home / ".claude" / "agents" / "developer.md").exists()

    @respx.mock
    def test_update_reports_all_up_to_date(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MANIFEST_WITH_REAL_SHA)
        )
        agents_dir = isolated_home / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "developer.md").write_text(_AGENT_CONTENT, encoding="utf-8")

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["agents", "update"])

        assert result.exit_code == 0, result.output
        assert "up-to-date" in result.output.lower()
