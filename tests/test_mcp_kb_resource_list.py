"""Tests for the ``kb_resource_list`` MCP tool handler.

Acceptance criteria covered:
- happy path: mix of up-to-date and outdated resources
- all up-to-date: shows "todos atualizados"
- missing manifest: still returns output (no error), treats all as "never pulled"
- server read error: returns error text, does not raise
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from oh_my_harness.kb.cli.resource.manifest import (
    Manifest,
    ResourceRecord,
    save_manifest,
)
from oh_my_harness.kb.cli.resource.registry import RESOURCE_REGISTRY
from oh_my_harness.kb.mcp.tools.kb_resource_list import handle_kb_resource_list

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONTENT_V1 = (
    "<!-- content_version: 1.0.0 | locale: pt-BR | updated: 2026-01-01 -->\n"
    "# Skill\n\nOriginal content.\n"
)
_CONTENT_V2 = (
    "<!-- content_version: 1.1.0 | locale: pt-BR | updated: 2026-06-01 -->\n"
    "# Skill\n\nNova seção.\n"
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
async def test_list_with_drift(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When skills/scribe is behind, shows ● desatualizado and count."""
    _make_drifted_manifest(fake_claude_home)

    def _mock_read(uri: str, locale: str = "pt-BR") -> str:
        return _CONTENT_V2  # server is at V2 for all resources

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _mock_read)

    result = await handle_kb_resource_list({})

    assert len(result) == 1
    text = result[0].text
    assert "desatualizado" in text
    assert "skills/scribe" in text
    assert "desatualizado(s)" in text
    assert "kb_resource_update" in text


@pytest.mark.asyncio
async def test_list_all_up_to_date(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all resources are synced, shows 'todos atualizados'."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V1,
    )

    result = await handle_kb_resource_list({})

    assert len(result) == 1
    text = result[0].text
    assert "atualizado" in text
    assert "Todos os resources estao atualizados." in text


@pytest.mark.asyncio
async def test_list_missing_manifest(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When manifest is absent, tool still works — treats local as '—'."""
    # No manifest created — fake_claude_home only has empty .claude dir

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V2,
    )

    result = await handle_kb_resource_list({})

    assert len(result) == 1
    text = result[0].text
    # No exception — tool returns structured output
    assert "Resources disponiveis" in text
    # Local version shown as placeholder
    assert "--" in text
    # Because local sha is empty, it's outdated
    assert "desatualizado" in text


@pytest.mark.asyncio
async def test_list_server_read_error(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When server read fails, tool returns error text — does not raise."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    def _failing_read(uri: str, locale: str = "pt-BR") -> str:
        raise RuntimeError("connection refused")

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _failing_read)

    result = await handle_kb_resource_list({})

    assert len(result) == 1
    text = result[0].text
    assert "erro ao ler servidor" in text
