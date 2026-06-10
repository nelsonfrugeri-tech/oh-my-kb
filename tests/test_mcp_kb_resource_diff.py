"""Tests for the ``kb_resource_diff`` MCP tool handler.

Acceptance criteria covered:
- happy path: drift detected, diff block returned with summary
- all up-to-date: shows "sem alterações" for all
- unknown resource short_id: returns text error with valid list
- missing manifest: returns instruction to run pull --all
- single resource by name: only that resource is diffed
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from oh_my_kb.cli.resource.manifest import (
    Manifest,
    ResourceRecord,
    save_manifest,
)
from oh_my_kb.cli.resource.registry import RESOURCE_REGISTRY
from oh_my_kb.mcp.tools.kb_resource_diff import handle_kb_resource_diff

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
    """skills/scribe is behind (local sha = V1); template is current."""
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
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diff_with_drift(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When skills/scribe has drift, diff block and summary are returned."""
    skill_dir = fake_claude_home / ".claude" / "skills" / "scribe"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_CONTENT_V1, encoding="utf-8")

    _make_drifted_manifest(fake_claude_home)

    def _mock_read(uri: str, locale: str = "pt-BR") -> str:
        if "SKILL.md" in uri:
            return _CONTENT_V2
        return _CONTENT_V2

    monkeypatch.setattr("oh_my_kb.mcp.resources.read_scribe_resource", _mock_read)

    result = await handle_kb_resource_diff({})

    assert len(result) == 1
    text = result[0].text
    assert "skills/scribe" in text
    assert "resource com alterações" in text


@pytest.mark.asyncio
async def test_diff_all_up_to_date(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all resources are synced, shows 'sem alterações' for each."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    monkeypatch.setattr(
        "oh_my_kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V1,
    )

    result = await handle_kb_resource_diff({})

    assert len(result) == 1
    text = result[0].text
    assert "sem alterações" in text


@pytest.mark.asyncio
async def test_diff_unknown_resource_returns_error_text(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown resource short_id returns text listing valid ids — does not raise."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    result = await handle_kb_resource_diff({"resource": "nao/existe"})

    assert len(result) == 1
    text = result[0].text
    assert "não encontrado" in text
    assert "nao/existe" in text
    assert "skills/scribe" in text


@pytest.mark.asyncio
async def test_diff_missing_manifest_returns_instruction(
    fake_claude_home: Path,
) -> None:
    """When manifest is absent, returns instruction to run pull --all."""
    # No manifest created
    result = await handle_kb_resource_diff({})

    assert len(result) == 1
    text = result[0].text
    assert "manifest não encontrado" in text
    assert "omk resource pull --all" in text


@pytest.mark.asyncio
async def test_diff_single_resource(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passing a valid resource short_id diffs only that resource."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    monkeypatch.setattr(
        "oh_my_kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V1,
    )

    result = await handle_kb_resource_diff({"resource": "skills/scribe"})

    assert len(result) == 1
    text = result[0].text
    assert "skills/scribe" in text
    # Summary should only count one resource
    assert "template" not in text
