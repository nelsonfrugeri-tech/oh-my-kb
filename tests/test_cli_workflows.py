"""Tests for ``omh workflows`` CLI commands."""

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

_WORKFLOW_CONTENT = "// create-feature workflow v1.0.0\nexport default async function run() {}\n"
_WORKFLOW_SHA = hashlib.sha256(_WORKFLOW_CONTENT.encode()).hexdigest()

_MANIFEST = {
    "schema_version": 1,
    "skills": [],
    "agents": [],
    "workflows": [
        {
            "name": "create-feature",
            "version": "1.0.0",
            "path": "assets/workflows/create-feature.ts",
            "sha256": "abc123",
        },
        {
            "name": "other-workflow",
            "version": "1.0.0",
            "path": "assets/workflows/other-workflow.ts",
            "sha256": "def456",
        },
    ],
}

_MANIFEST_WITH_REAL_SHA = {
    "schema_version": 1,
    "skills": [],
    "agents": [],
    "workflows": [
        {
            "name": "create-feature",
            "version": "1.0.0",
            "path": "assets/workflows/create-feature.ts",
            "sha256": _WORKFLOW_SHA,
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


class TestWorkflowsList:
    @respx.mock
    def test_list_shows_workflows(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "list"])

        assert result.exit_code == 0, result.output
        assert "create-feature" in result.output
        assert "other-workflow" in result.output
        assert "1.0.0" in result.output

    @respx.mock
    def test_list_shows_not_installed(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "list"])

        assert "not-installed" in result.output

    @respx.mock
    def test_list_shows_up_to_date_when_matching(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MANIFEST_WITH_REAL_SHA)
        )
        workflows_dir = isolated_home / ".claude" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "create-feature.ts").write_text(_WORKFLOW_CONTENT, encoding="utf-8")

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "list"])

        assert "up-to-date" in result.output

    @respx.mock
    def test_list_shows_drift_when_sha_differs(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        workflows_dir = isolated_home / ".claude" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "create-feature.ts").write_text("different content", encoding="utf-8")

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "list"])

        assert "drift" in result.output

    @respx.mock
    def test_list_exits_nonzero_on_network_error(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(500, text="error"))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "list"])

        assert result.exit_code != 0


class TestWorkflowsPull:
    @respx.mock
    def test_pull_single_downloads_file(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        workflow_url = f"{RAW_BASE_URL}/assets/workflows/create-feature.ts"
        respx.get(workflow_url).mock(
            return_value=httpx.Response(200, text=_WORKFLOW_CONTENT)
        )

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "pull", "create-feature"])

        assert result.exit_code == 0, result.output
        workflow_ts = isolated_home / ".claude" / "workflows" / "create-feature.ts"
        assert workflow_ts.exists()
        assert workflow_ts.read_text() == _WORKFLOW_CONTENT

    @respx.mock
    def test_pull_all_downloads_all_workflows(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        for name in ["create-feature", "other-workflow"]:
            url = f"{RAW_BASE_URL}/assets/workflows/{name}.ts"
            respx.get(url).mock(return_value=httpx.Response(200, text=f"// {name}"))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "pull", "--all"])

        assert result.exit_code == 0, result.output
        assert (isolated_home / ".claude" / "workflows" / "create-feature.ts").exists()
        assert (isolated_home / ".claude" / "workflows" / "other-workflow.ts").exists()

    @respx.mock
    def test_pull_unknown_workflow_exits_nonzero(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "pull", "nonexistent"])

        assert result.exit_code != 0

    @respx.mock
    def test_pull_without_args_exits_nonzero(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "pull"])

        assert result.exit_code != 0


class TestWorkflowsDiff:
    @respx.mock
    def test_diff_shows_all_workflows(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "diff"])

        assert result.exit_code == 0, result.output
        assert "create-feature" in result.output
        assert "other-workflow" in result.output

    @respx.mock
    def test_diff_single_workflow(self, runner: CliRunner, isolated_home: Path) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "diff", "create-feature"])

        assert result.exit_code == 0, result.output
        assert "create-feature" in result.output
        assert "other-workflow" not in result.output

    @respx.mock
    def test_diff_unknown_workflow_exits_nonzero(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "diff", "nonexistent"])

        assert result.exit_code != 0


class TestWorkflowsUpdate:
    @respx.mock
    def test_update_pulls_not_installed(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        for name in ["create-feature", "other-workflow"]:
            url = f"{RAW_BASE_URL}/assets/workflows/{name}.ts"
            respx.get(url).mock(return_value=httpx.Response(200, text=f"// {name}"))

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "update"])

        assert result.exit_code == 0, result.output
        assert (isolated_home / ".claude" / "workflows" / "create-feature.ts").exists()

    @respx.mock
    def test_update_reports_all_up_to_date(
        self, runner: CliRunner, isolated_home: Path
    ) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MANIFEST_WITH_REAL_SHA)
        )
        workflows_dir = isolated_home / ".claude" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "create-feature.ts").write_text(_WORKFLOW_CONTENT, encoding="utf-8")

        with patch.object(Path, "home", return_value=isolated_home):
            result = runner.invoke(app, ["workflows", "update"])

        assert result.exit_code == 0, result.output
        assert "up-to-date" in result.output.lower()
