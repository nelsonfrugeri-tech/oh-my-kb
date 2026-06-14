"""Verify that ``omh install --yes`` automatically downloads skills, agents and workflows."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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
            "files": [{"path": "SKILL.md", "sha256": "abc"}],
        }
    ],
    "agents": [
        {
            "name": "developer",
            "version": "1.0.0",
            "path": "assets/agents/developer.md",
            "sha256": "def",
        }
    ],
    "workflows": [
        {
            "name": "create-feature",
            "version": "1.0.0",
            "path": "assets/workflows/create-feature.ts",
            "sha256": "ghi",
        }
    ],
}


def _fake_docker() -> MagicMock:
    client = MagicMock()
    container = MagicMock()
    container.status = "running"
    container.short_id = "abc123"
    client.containers.get.return_value = container
    client.images.get.return_value = MagicMock()
    return client


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestInstallPullsAssets:
    @respx.mock
    def test_install_downloads_skills_agents_and_workflows(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_docker()

        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        respx.get(f"{RAW_BASE_URL}/assets/skills/python/SKILL.md").mock(
            return_value=httpx.Response(200, text="# Python Skill")
        )
        respx.get(f"{RAW_BASE_URL}/assets/agents/developer.md").mock(
            return_value=httpx.Response(200, text="# Developer Agent")
        )
        respx.get(f"{RAW_BASE_URL}/assets/workflows/create-feature.ts").mock(
            return_value=httpx.Response(200, text="// create-feature workflow")
        )

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_harness.kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_harness.kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_harness.kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_harness.kb.storage.QdrantStore.ensure_collection"),
        ):
            result = runner.invoke(app, ["install", "--yes"])

        assert result.exit_code == 0, result.output
        skill_file = home / ".claude" / "skills" / "python" / "SKILL.md"
        agent_file = home / ".claude" / "agents" / "developer.md"
        workflow_file = home / ".claude" / "workflows" / "create-feature.ts"
        assert skill_file.exists(), f"skill file not created at {skill_file}"
        assert agent_file.exists(), f"agent file not created at {agent_file}"
        assert workflow_file.exists(), f"workflow file not created at {workflow_file}"

    @respx.mock
    def test_install_does_not_fail_on_network_error(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Install must exit 0 even if the manifest fetch fails during step 8."""
        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_docker()

        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(503, text="down"))

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_harness.kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_harness.kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_harness.kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_harness.kb.storage.QdrantStore.ensure_collection"),
        ):
            result = runner.invoke(app, ["install", "--yes"])

        assert result.exit_code == 0, result.output
        assert "[8/9]" in result.output

    @respx.mock
    def test_install_output_mentions_step_8(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        home = tmp_path / "home"
        home.mkdir()
        fake_client = _fake_docker()

        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(200, json=_MANIFEST))
        respx.get(f"{RAW_BASE_URL}/assets/skills/python/SKILL.md").mock(
            return_value=httpx.Response(200, text="# Python")
        )
        respx.get(f"{RAW_BASE_URL}/assets/agents/developer.md").mock(
            return_value=httpx.Response(200, text="# Developer")
        )
        respx.get(f"{RAW_BASE_URL}/assets/workflows/create-feature.ts").mock(
            return_value=httpx.Response(200, text="// create-feature")
        )

        with (
            patch.object(Path, "home", return_value=home),
            patch(
                "oh_my_harness.kb.infra.docker_qdrant.QdrantContainer._docker",
                return_value=fake_client,
            ),
            patch("oh_my_harness.kb.storage.QdrantStore.healthcheck", return_value=True),
            patch("oh_my_harness.kb.storage.QdrantStore.collection_exists", return_value=True),
            patch("oh_my_harness.kb.storage.QdrantStore.ensure_collection"),
        ):
            result = runner.invoke(app, ["install", "--yes"])

        assert "[8/9]" in result.output
