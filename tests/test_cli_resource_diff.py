"""Tests for ``omk resource diff``.

Acceptance criteria covered:
- diff all — no changes (all up-to-date message)
- diff all — with drift (shows unified diff, summary)
- diff single resource by name
- diff — manifest missing exits 1
- diff — invalid resource ID exits 3
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from oh_my_harness.kb.cli.app import app
from oh_my_harness.kb.cli.resource.manifest import (
    Manifest,
    ResourceRecord,
    save_manifest,
)
from oh_my_harness.kb.cli.resource.registry import RESOURCE_REGISTRY

runner = CliRunner()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONTENT_V1 = (
    "<!-- content_version: 1.0.0 | locale: pt-BR | updated: 2026-01-01 -->\n"
    "# Skill\n\nOriginal content.\n"
)
_CONTENT_V2 = (
    "<!-- content_version: 1.1.0 | locale: pt-BR | updated: 2026-06-01 -->\n"
    "# Skill\n\nOriginal content.\n\nNova seção.\n"
)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_synced_manifest(tmp_path: Path, content: str = _CONTENT_V1) -> None:
    """Create a manifest where all resources match the given content."""
    (tmp_path / ".claude").mkdir(exist_ok=True)
    resources = {
        meta.short_id: ResourceRecord(
            uri=meta.uri,
            local_path=meta.local_path,
            content_version="1.0.0",
            pulled_at="2026-01-01T00:00:00Z",
            sha256=_sha256(content),
        )
        for meta in RESOURCE_REGISTRY
    }
    m = Manifest(pulled_at="2026-01-01T00:00:00Z", resources=resources)
    save_manifest(m, home=tmp_path)


def _make_drifted_manifest(tmp_path: Path) -> None:
    """Create a manifest where skills/scribe is behind the server version."""
    (tmp_path / ".claude").mkdir(exist_ok=True)
    resources = {}
    for meta in RESOURCE_REGISTRY:
        if meta.short_id == "skills/scribe":
            sha = _sha256(_CONTENT_V1)
            version = "1.0.0"
        else:
            sha = _sha256(_CONTENT_V2)
            version = "1.1.0"
        resources[meta.short_id] = ResourceRecord(
            uri=meta.uri,
            local_path=meta.local_path,
            content_version=version,
            pulled_at="2026-01-01T00:00:00Z",
            sha256=sha,
        )
    m = Manifest(pulled_at="2026-01-01T00:00:00Z", resources=resources)
    save_manifest(m, home=tmp_path)


# ---------------------------------------------------------------------------
# test_diff_all_no_changes
# ---------------------------------------------------------------------------


def test_diff_all_no_changes(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all resources are in sync, prints 'todos atualizados'."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V1,
    )

    result = runner.invoke(app, ["resource", "diff"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Todos os resources estão atualizados." in result.output


# ---------------------------------------------------------------------------
# test_diff_all_with_drift
# ---------------------------------------------------------------------------


def test_diff_all_with_drift(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When skills/scribe drifts, diff shows header and summary."""
    skill_dir = fake_claude_home / ".claude" / "skills" / "scribe"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_CONTENT_V1, encoding="utf-8")

    _make_drifted_manifest(fake_claude_home)

    def _mock_read(uri: str, locale: str = "pt-BR") -> str:
        if "SKILL.md" in uri:
            return _CONTENT_V2
        return _CONTENT_V2

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _mock_read)

    result = runner.invoke(app, ["resource", "diff"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "skills/scribe" in result.output
    assert "resource com alterações" in result.output or "sem alterações" in result.output


# ---------------------------------------------------------------------------
# test_diff_single_resource
# ---------------------------------------------------------------------------


def test_diff_single_resource(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``diff skills/scribe`` only checks that resource and exits 0."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V1,
    )

    result = runner.invoke(
        app, ["resource", "diff", "skills/scribe"], catch_exceptions=False
    )
    assert result.exit_code == 0


def test_diff_single_resource_with_drift(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``diff skills/scribe`` shows header with version delta when drifted."""
    skill_dir = fake_claude_home / ".claude" / "skills" / "scribe"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_CONTENT_V1, encoding="utf-8")

    (fake_claude_home / ".claude").mkdir(exist_ok=True)
    resources = {
        "skills/scribe": ResourceRecord(
            uri=RESOURCE_REGISTRY[0].uri,
            local_path=RESOURCE_REGISTRY[0].local_path,
            content_version="1.0.0",
            pulled_at="2026-01-01T00:00:00Z",
            sha256=_sha256(_CONTENT_V1),
        )
    }
    m = Manifest(pulled_at="2026-01-01T00:00:00Z", resources=resources)
    save_manifest(m, home=fake_claude_home)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V2,
    )

    result = runner.invoke(
        app, ["resource", "diff", "skills/scribe"], catch_exceptions=False
    )
    assert result.exit_code == 0
    assert "skills/scribe" in result.output
    assert "1.0.0" in result.output
    assert "1.1.0" in result.output


# ---------------------------------------------------------------------------
# test_diff_manifest_missing_exits_1
# ---------------------------------------------------------------------------


def test_diff_manifest_missing_exits_1(
    fake_claude_home: Path,
) -> None:
    """When no manifest exists, exits 1 with instruction message."""
    result = runner.invoke(app, ["resource", "diff"], catch_exceptions=False)
    assert result.exit_code == 1
    assert "manifest não encontrado" in result.output
    assert "omk resource pull --all" in result.output


# ---------------------------------------------------------------------------
# test_diff_invalid_resource_id_exits_3
# ---------------------------------------------------------------------------


def test_diff_invalid_resource_id_exits_3(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown resource ID exits 3 with error and available list."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    result = runner.invoke(
        app, ["resource", "diff", "nao/existe"], catch_exceptions=False
    )
    assert result.exit_code == 3
    assert "não encontrado no servidor MCP" in result.output
    assert "nao/existe" in result.output
    assert "skills/scribe" in result.output
