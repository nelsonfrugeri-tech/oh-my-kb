"""Tests for the ``kb_resource_update`` MCP tool handler.

Acceptance criteria covered:
- happy path with drift: writes file, updates manifest, calls _regenerate_claude_md
- all up-to-date: all resources show ○ sem alterações
- unknown resource short_id: returns text error with valid list
- missing manifest: returns instruction to run pull --all
- _regenerate_claude_md failure: warns but returns a valid response (does not raise)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from oh_my_harness.kb.cli.resource.manifest import (
    Manifest,
    ResourceRecord,
    load_manifest,
    save_manifest,
)
from oh_my_harness.kb.cli.resource.registry import RESOURCE_REGISTRY
from oh_my_harness.kb.mcp.tools.kb_resource_update import handle_kb_resource_update

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
    """skills/scribe is behind (local sha = V1); template is current (V2)."""
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
async def test_update_with_drift_writes_file_and_manifest(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drift detected → file written, manifest updated, regenerate called."""
    _make_drifted_manifest(fake_claude_home)

    def _mock_read(uri: str, locale: str = "pt-BR") -> str:
        return _CONTENT_V2

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _mock_read)

    regenerate_calls: list[tuple] = []

    def _mock_regenerate(home: Path | None = None) -> None:
        regenerate_calls.append((home,))

    import oh_my_harness.kb.mcp.tools.kb_resource_update as _mcp_mod
    monkeypatch.setattr(_mcp_mod, "_regenerate_claude_md", _mock_regenerate)

    result = await handle_kb_resource_update({})

    assert len(result) == 1
    text = result[0].text
    assert "ok" in text
    assert "1.0.0 -> 1.1.0" in text
    assert "atualizado" in text

    # Manifest must be updated
    updated = load_manifest(home=fake_claude_home)
    assert updated is not None
    assert updated.resources["skills/scribe"].sha256 == _sha256(_CONTENT_V2)
    assert updated.resources["skills/scribe"].content_version == "1.1.0"

    # _regenerate_claude_md must have been called exactly once
    assert len(regenerate_calls) == 1


@pytest.mark.asyncio
async def test_update_all_up_to_date(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no drift, all resources show ○ sem alterações."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V1,
    )

    result = await handle_kb_resource_update({})

    assert len(result) == 1
    text = result[0].text
    assert "o " in text
    assert "sem alteracoes" in text
    assert "ok" not in text


@pytest.mark.asyncio
async def test_update_unknown_resource_returns_error_text(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown resource short_id returns text error with valid list."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    result = await handle_kb_resource_update({"resource": "nao/existe"})

    assert len(result) == 1
    text = result[0].text
    assert "nao encontrado" in text
    assert "nao/existe" in text
    assert "skills/scribe" in text


@pytest.mark.asyncio
async def test_update_missing_manifest_returns_instruction(
    fake_claude_home: Path,
) -> None:
    """When manifest is absent, returns instruction to run pull --all."""
    result = await handle_kb_resource_update({})

    assert len(result) == 1
    text = result[0].text
    assert "manifest nao encontrado" in text
    assert "omk resource pull --all" in text


@pytest.mark.asyncio
async def test_update_regenerate_failure_warns_but_succeeds(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If _regenerate_claude_md raises, a warning is included but tool returns 200-style."""
    _make_drifted_manifest(fake_claude_home)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V2,
    )

    def _failing_regenerate(home: Path | None = None) -> None:
        raise RuntimeError("config not found")

    import oh_my_harness.kb.mcp.tools.kb_resource_update as _mcp_mod
    monkeypatch.setattr(_mcp_mod, "_regenerate_claude_md", _failing_regenerate)

    result = await handle_kb_resource_update({})

    # Tool must not raise
    assert len(result) == 1
    text = result[0].text
    # Warning about CLAUDE.md regeneration failure should appear
    assert "Aviso" in text or "nao pode ser regenerado" in text
    # But the update itself succeeded
    assert "ok" in text or "atualizado" in text
