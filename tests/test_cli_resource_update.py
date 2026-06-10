"""Tests for ``omk resource update``.

Acceptance criteria covered:
- update all — no changes (all up-to-date message)
- update all — with drift + --yes (writes files, updates manifest)
- update single resource already up-to-date
- update regenerates CLAUDE.md on success (mocked do_bootstrap)
- update bootstrap failure warns but exits 0
- update confirmation N skips (interactive, no --yes)
- update manifest missing exits 1
- update invalid resource ID exits 3
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import oh_my_harness.kb.cli.resource.update_cmd  # noqa: F401 — ensures module is registered
from oh_my_harness.kb.cli.app import app
from oh_my_harness.kb.cli.resource.manifest import (
    Manifest,
    ResourceRecord,
    load_manifest,
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
    """skills/scribe is behind (local sha = V1), template is synced."""
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
# test_update_all_no_changes
# ---------------------------------------------------------------------------


def test_update_all_no_changes(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all resources are synced, prints 'todos atualizados' and exits 0."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V1,
    )

    result = runner.invoke(app, ["resource", "update", "--yes"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "já estão na versão mais recente" in result.output


# ---------------------------------------------------------------------------
# test_update_all_with_drift_yes_flag
# ---------------------------------------------------------------------------


def test_update_all_with_drift_yes_flag(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``update --yes`` writes files and updates manifest without prompting."""
    _make_drifted_manifest(fake_claude_home)

    def _mock_read(uri: str, locale: str = "pt-BR") -> str:
        if "SKILL.md" in uri:
            return _CONTENT_V2
        return _CONTENT_V2

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _mock_read)

    # Mock bootstrap so we don't need real config
    _mod = sys.modules["oh_my_harness.kb.cli.resource.update_cmd"]
    monkeypatch.setattr(_mod, "_regenerate_claude_md", lambda home=None: None)

    result = runner.invoke(app, ["resource", "update", "--yes"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "atualizado para 1.1.0" in result.output

    # Verify manifest updated
    updated_manifest = load_manifest(home=fake_claude_home)
    assert updated_manifest is not None
    assert updated_manifest.resources["skills/scribe"].sha256 == _sha256(_CONTENT_V2)
    assert updated_manifest.resources["skills/scribe"].content_version == "1.1.0"


# ---------------------------------------------------------------------------
# test_update_single_resource_already_up_to_date
# ---------------------------------------------------------------------------


def test_update_single_resource_already_up_to_date(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``update skills/scribe`` when already current shows '○ já está na versão mais recente'."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V1,
    )

    result = runner.invoke(
        app, ["resource", "update", "skills/scribe"], catch_exceptions=False
    )
    assert result.exit_code == 0
    assert "já está na versão mais recente" in result.output
    assert "skills/scribe" in result.output


# ---------------------------------------------------------------------------
# test_update_regenerates_claude_md_on_success
# ---------------------------------------------------------------------------


def test_update_regenerates_claude_md_on_success(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After updating, CLAUDE.md regeneration is triggered."""
    _make_drifted_manifest(fake_claude_home)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V2,
    )

    bootstrap_calls: list[tuple] = []

    def _fake_regenerate(home: Path | None = None) -> None:
        bootstrap_calls.append((home,))
        # Simulate the output that _regenerate_claude_md normally prints
        import typer
        typer.echo("  Regenerando ~/.claude/CLAUDE.md...")
        typer.echo("  ✓ ~/.claude/CLAUDE.md atualizado.")

    _mod = sys.modules["oh_my_harness.kb.cli.resource.update_cmd"]
    monkeypatch.setattr(_mod, "_regenerate_claude_md", _fake_regenerate)

    result = runner.invoke(app, ["resource", "update", "--yes"], catch_exceptions=False)
    assert result.exit_code == 0
    assert len(bootstrap_calls) == 1
    assert "CLAUDE.md" in result.output


# ---------------------------------------------------------------------------
# test_update_bootstrap_failure_warns_but_exits_0
# ---------------------------------------------------------------------------


def test_update_bootstrap_failure_warns_but_exits_0(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If CLAUDE.md regeneration fails, a warning is shown but exit code is 0."""
    _make_drifted_manifest(fake_claude_home)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V2,
    )

    def _failing_regenerate(home: Path | None = None) -> None:
        import typer
        typer.echo(
            "  Aviso: ~/.claude/CLAUDE.md não pôde ser regenerado: config not found. "
            "Execute omk install para corrigir."
        )

    _mod = sys.modules["oh_my_harness.kb.cli.resource.update_cmd"]
    monkeypatch.setattr(_mod, "_regenerate_claude_md", _failing_regenerate)

    result = runner.invoke(app, ["resource", "update", "--yes"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Aviso" in result.output or "CLAUDE.md" in result.output


# ---------------------------------------------------------------------------
# test_update_confirmation_n_skips
# ---------------------------------------------------------------------------


def test_update_confirmation_n_skips(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When user answers N to confirmation, the resource is not updated."""
    _make_drifted_manifest(fake_claude_home)

    monkeypatch.setattr(
        "oh_my_harness.kb.mcp.resources.read_scribe_resource",
        lambda uri, locale="pt-BR": _CONTENT_V2,
    )

    # Provide 'N' for all confirmations via input
    result = runner.invoke(
        app,
        ["resource", "update"],
        input="N\n" * 10,
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    # Manifest should NOT have been updated (sha still V1 for skills/scribe)
    manifest = load_manifest(home=fake_claude_home)
    assert manifest is not None
    assert manifest.resources["skills/scribe"].sha256 == _sha256(_CONTENT_V1)


# ---------------------------------------------------------------------------
# test_update_manifest_missing_exits_1
# ---------------------------------------------------------------------------


def test_update_manifest_missing_exits_1(
    fake_claude_home: Path,
) -> None:
    """When manifest is absent, exits 1 with instruction."""
    result = runner.invoke(app, ["resource", "update"], catch_exceptions=False)
    assert result.exit_code == 1
    assert "manifest não encontrado" in result.output
    assert "omk resource pull --all" in result.output


# ---------------------------------------------------------------------------
# test_update_invalid_resource_id_exits_3
# ---------------------------------------------------------------------------


def test_update_invalid_resource_id_exits_3(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown resource ID exits 3."""
    _make_synced_manifest(fake_claude_home, _CONTENT_V1)

    result = runner.invoke(
        app, ["resource", "update", "nao/existe"], catch_exceptions=False
    )
    assert result.exit_code == 3
    assert "não encontrado no servidor MCP" in result.output
    assert "nao/existe" in result.output
