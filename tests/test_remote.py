"""Tests for oh_my_harness.kb.cli._remote — fetch_text and load_remote_manifest."""

from __future__ import annotations

import httpx
import pytest
import respx

from oh_my_harness.kb.cli._remote import (
    MANIFEST_URL,
    AgentEntry,
    Manifest,
    SkillEntry,
    SkillFile,
    WorkflowEntry,
    fetch_text,
    load_remote_manifest,
)

_MINIMAL_MANIFEST = {
    "schema_version": 1,
    "skills": [
        {
            "name": "python",
            "version": "1.0.0",
            "path": "assets/skills/python",
            "files": [{"path": "SKILL.md", "sha256": "abc123"}],
        }
    ],
    "agents": [
        {
            "name": "developer",
            "version": "1.0.0",
            "path": "assets/agents/developer.md",
            "sha256": "def456",
        }
    ],
    "workflows": [
        {
            "name": "create-feature",
            "version": "1.0.0",
            "path": "assets/workflows/create-feature.ts",
            "sha256": "ghi789",
        }
    ],
}

_MANIFEST_WITHOUT_WORKFLOWS = {
    "schema_version": 1,
    "skills": [],
    "agents": [],
}


class TestFetchText:
    @respx.mock
    def test_returns_body_on_200(self) -> None:
        respx.get("https://example.com/file.txt").mock(
            return_value=httpx.Response(200, text="hello world")
        )
        assert fetch_text("https://example.com/file.txt") == "hello world"

    @respx.mock
    def test_raises_on_404(self) -> None:
        respx.get("https://example.com/missing.txt").mock(
            return_value=httpx.Response(404, text="not found")
        )
        with pytest.raises(RuntimeError, match="404"):
            fetch_text("https://example.com/missing.txt")

    @respx.mock
    def test_raises_on_500(self) -> None:
        respx.get("https://example.com/error.txt").mock(
            return_value=httpx.Response(500, text="server error")
        )
        with pytest.raises(RuntimeError, match="500"):
            fetch_text("https://example.com/error.txt")

    @respx.mock
    def test_raises_on_timeout(self) -> None:
        respx.get("https://example.com/slow.txt").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        with pytest.raises(RuntimeError, match="timed out"):
            fetch_text("https://example.com/slow.txt")

    @respx.mock
    def test_raises_on_network_error(self) -> None:
        respx.get("https://example.com/bad.txt").mock(
            side_effect=httpx.ConnectError("connect failed")
        )
        with pytest.raises(RuntimeError, match="network error"):
            fetch_text("https://example.com/bad.txt")


class TestLoadRemoteManifest:
    @respx.mock
    def test_parses_manifest_correctly(self) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MINIMAL_MANIFEST)
        )
        manifest = load_remote_manifest()
        assert isinstance(manifest, Manifest)
        assert manifest.schema_version == 1
        assert len(manifest.skills) == 1
        assert len(manifest.agents) == 1
        assert len(manifest.workflows) == 1

    @respx.mock
    def test_skill_entry_fields(self) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MINIMAL_MANIFEST)
        )
        manifest = load_remote_manifest()
        skill = manifest.skills[0]
        assert isinstance(skill, SkillEntry)
        assert skill.name == "python"
        assert skill.version == "1.0.0"
        assert len(skill.files) == 1
        assert isinstance(skill.files[0], SkillFile)
        assert skill.files[0].path == "SKILL.md"
        assert skill.files[0].sha256 == "abc123"

    @respx.mock
    def test_agent_entry_fields(self) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MINIMAL_MANIFEST)
        )
        manifest = load_remote_manifest()
        agent = manifest.agents[0]
        assert isinstance(agent, AgentEntry)
        assert agent.name == "developer"
        assert agent.version == "1.0.0"
        assert agent.sha256 == "def456"

    @respx.mock
    def test_workflow_entry_fields(self) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MINIMAL_MANIFEST)
        )
        manifest = load_remote_manifest()
        workflow = manifest.workflows[0]
        assert isinstance(workflow, WorkflowEntry)
        assert workflow.name == "create-feature"
        assert workflow.version == "1.0.0"
        assert workflow.path == "assets/workflows/create-feature.ts"
        assert workflow.sha256 == "ghi789"

    @respx.mock
    def test_workflows_defaults_to_empty_list_when_absent(self) -> None:
        """Older manifests without 'workflows' key must not break parsing."""
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, json=_MANIFEST_WITHOUT_WORKFLOWS)
        )
        manifest = load_remote_manifest()
        assert manifest.workflows == []

    @respx.mock
    def test_raises_on_invalid_json(self) -> None:
        respx.get(MANIFEST_URL).mock(
            return_value=httpx.Response(200, text="not json {{{")
        )
        with pytest.raises(RuntimeError, match="invalid JSON"):
            load_remote_manifest()

    @respx.mock
    def test_raises_on_http_error(self) -> None:
        respx.get(MANIFEST_URL).mock(return_value=httpx.Response(503, text="unavailable"))
        with pytest.raises(RuntimeError, match="503"):
            load_remote_manifest()
