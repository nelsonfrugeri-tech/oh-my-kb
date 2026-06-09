"""Tests for oh_my_kb.cli.resource (omk resource sub-commands).

All tests use Typer's CliRunner so the full CLI path is exercised without
touching the real ~/.claude/ directory.  The MCP server layer is called
directly (not over stdio), so no MCP server process is needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from oh_my_kb.cli.manifest import Manifest, save_manifest, upsert_entry
from oh_my_kb.cli.resource import _ID_TO_LOCAL_PATH, _section_header, app
from oh_my_kb.mcp.resources import (
    SCRIBE_SKILL_URI,
    SCRIBE_TEMPLATE_URI,
    compute_sha256,
    read_scribe_resource,
    resource_meta,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest_with_current_versions(tmp_path: Path) -> Manifest:
    """Build a manifest matching server versions exactly (sha256 current)."""
    m = Manifest()
    for resource_id, uri in [
        ("skills/scribe", SCRIBE_SKILL_URI),
        ("skills/scribe-template", SCRIBE_TEMPLATE_URI),
    ]:
        content = read_scribe_resource(uri)
        sha = compute_sha256(content)
        meta = resource_meta(uri)
        upsert_entry(
            manifest=m,
            resource_id=resource_id,
            uri=uri,
            local_path=_ID_TO_LOCAL_PATH[resource_id],
            content_version=meta.content_version,
            sha256=sha,
        )
    save_manifest(m, home=tmp_path)
    return m


def _make_manifest_with_stale_versions(tmp_path: Path) -> Manifest:
    """Build a manifest with a wrong sha256 to simulate drift."""
    m = Manifest()
    upsert_entry(
        manifest=m,
        resource_id="skills/scribe",
        uri=SCRIBE_SKILL_URI,
        local_path="~/.claude/skills/scribe/SKILL.md",
        content_version="0.9.0",
        sha256="0" * 64,  # wrong sha — will appear as changed
    )
    upsert_entry(
        manifest=m,
        resource_id="skills/scribe-template",
        uri=SCRIBE_TEMPLATE_URI,
        local_path="~/.claude/skills/scribe/template.md",
        content_version="1.0.0",
        sha256=compute_sha256(read_scribe_resource(SCRIBE_TEMPLATE_URI)),
    )
    save_manifest(m, home=tmp_path)
    return m


# ---------------------------------------------------------------------------
# _section_header
# ---------------------------------------------------------------------------


def test_section_header_is_80_chars() -> None:
    header = _section_header("skills/scribe  (local: 1.0.0  →  servidor: 1.1.0)")
    assert len(header) <= 80 + 10  # allow for unicode width variation


def test_section_header_starts_with_box_drawing() -> None:
    header = _section_header("test")
    assert header.startswith("───")


# ---------------------------------------------------------------------------
# omk resource list
# ---------------------------------------------------------------------------


def test_list_shows_resources() -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    assert "skills/scribe" in result.output
    assert "skills/scribe-template" in result.output


def test_list_shows_version() -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "v1.0.0" in result.output


def test_list_shows_resource_count() -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "resources encontrados" in result.output


# ---------------------------------------------------------------------------
# omk resource pull
# ---------------------------------------------------------------------------


def test_pull_single_resource(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = runner.invoke(app, ["pull", "skills/scribe"])
    assert result.exit_code == 0, result.output
    dest = tmp_path / ".claude" / "skills" / "scribe" / "SKILL.md"
    assert dest.exists()
    assert "Scribe" in dest.read_text(encoding="utf-8")


def test_pull_single_creates_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner.invoke(app, ["pull", "skills/scribe"])
    manifest_file = tmp_path / ".claude" / ".omk-manifest.json"
    assert manifest_file.exists()
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert "skills/scribe" in data["resources"]
    assert data["resources"]["skills/scribe"]["content_version"] == "1.0.0"


def test_pull_all_downloads_all_resources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = runner.invoke(app, ["pull", "--all"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude" / "skills" / "scribe" / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "skills" / "scribe" / "template.md").exists()


def test_pull_all_updates_manifest_with_two_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner.invoke(app, ["pull", "--all"])
    manifest_file = tmp_path / ".claude" / ".omk-manifest.json"
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert "skills/scribe" in data["resources"]
    assert "skills/scribe-template" in data["resources"]


def test_pull_invalid_resource_exits_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = runner.invoke(app, ["pull", "nonexistent/resource"])
    assert result.exit_code == 3


def test_pull_stdout_does_not_write_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = runner.invoke(app, ["pull", "--stdout", "skills/scribe"])
    assert result.exit_code == 0
    dest = tmp_path / ".claude" / "skills" / "scribe" / "SKILL.md"
    assert not dest.exists()
    assert "Scribe" in result.output


def test_pull_no_resource_no_all_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = runner.invoke(app, ["pull"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# omk resource diff — manifest absent
# ---------------------------------------------------------------------------


def test_diff_without_manifest_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = runner.invoke(app, ["diff"])
    assert result.exit_code == 1
    assert "manifest não encontrado" in result.output


# ---------------------------------------------------------------------------
# omk resource diff — all up to date
# ---------------------------------------------------------------------------


def test_diff_all_up_to_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_current_versions(tmp_path)
    result = runner.invoke(app, ["diff"])
    assert result.exit_code == 0, result.output
    assert "atualizados" in result.output


# ---------------------------------------------------------------------------
# omk resource diff — with changes
# ---------------------------------------------------------------------------


def test_diff_shows_changed_resource(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_stale_versions(tmp_path)
    result = runner.invoke(app, ["diff"])
    assert result.exit_code == 0, result.output
    assert "skills/scribe" in result.output
    # Should show the version change arrow
    assert "→" in result.output or "alterações" in result.output


def test_diff_single_resource(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_current_versions(tmp_path)
    result = runner.invoke(app, ["diff", "skills/scribe"])
    assert result.exit_code == 0, result.output


def test_diff_invalid_resource_exits_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_current_versions(tmp_path)
    result = runner.invoke(app, ["diff", "nonexistent/resource"])
    assert result.exit_code == 3


# ---------------------------------------------------------------------------
# omk resource update — manifest absent
# ---------------------------------------------------------------------------


def test_update_without_manifest_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 1
    assert "manifest não encontrado" in result.output


# ---------------------------------------------------------------------------
# omk resource update — all up to date
# ---------------------------------------------------------------------------


def test_update_all_up_to_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_current_versions(tmp_path)
    result = runner.invoke(app, ["update", "--yes"])
    assert result.exit_code == 0, result.output
    assert "atualizados" in result.output.lower()


# ---------------------------------------------------------------------------
# omk resource update — single resource already up to date
# ---------------------------------------------------------------------------


def test_update_single_already_up_to_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_current_versions(tmp_path)
    result = runner.invoke(app, ["update", "skills/scribe-template"])
    assert result.exit_code == 0, result.output
    assert "versão mais recente" in result.output


# ---------------------------------------------------------------------------
# omk resource update --yes — applies without prompting
# ---------------------------------------------------------------------------


def test_update_yes_applies_changed_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_stale_versions(tmp_path)

    # Write stale local file for skills/scribe
    dest = tmp_path / ".claude" / "skills" / "scribe" / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("old content", encoding="utf-8")

    # Mock bootstrap to avoid needing a real universe config
    with patch("oh_my_kb.cli.resource._do_regenerate_claude_md"):
        result = runner.invoke(app, ["update", "--yes"])

    assert result.exit_code == 0, result.output
    assert "atualizado" in result.output.lower()
    # File should now contain real server content
    assert "Scribe" in dest.read_text(encoding="utf-8")


def test_update_yes_saves_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_stale_versions(tmp_path)

    with patch("oh_my_kb.cli.resource._do_regenerate_claude_md"):
        runner.invoke(app, ["update", "--yes"])

    manifest_file = tmp_path / ".claude" / ".omk-manifest.json"
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    # sha256 should now match the real server content
    from oh_my_kb.mcp.resources import read_scribe_resource
    expected_sha = compute_sha256(read_scribe_resource(SCRIBE_SKILL_URI))
    assert data["resources"]["skills/scribe"]["sha256"] == expected_sha


# ---------------------------------------------------------------------------
# omk resource update — interactive confirmation (default N skips)
# ---------------------------------------------------------------------------


def test_update_interactive_default_n_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_stale_versions(tmp_path)

    # Enter → default N
    result = runner.invoke(app, ["update"], input="\n")
    assert result.exit_code == 0, result.output
    # skills/scribe should NOT be updated (no sha256 change)
    manifest_file = tmp_path / ".claude" / ".omk-manifest.json"
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert data["resources"]["skills/scribe"]["sha256"] == "0" * 64


def test_update_interactive_s_confirms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_stale_versions(tmp_path)

    dest = tmp_path / ".claude" / "skills" / "scribe" / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("old", encoding="utf-8")

    with patch("oh_my_kb.cli.resource._do_regenerate_claude_md"):
        result = runner.invoke(app, ["update"], input="s\n")

    assert result.exit_code == 0, result.output
    assert "Scribe" in dest.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# omk resource update — invalid resource
# ---------------------------------------------------------------------------


def test_update_invalid_resource_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_current_versions(tmp_path)
    result = runner.invoke(app, ["update", "nonexistent/resource"])
    assert result.exit_code == 3


# ---------------------------------------------------------------------------
# Regression: orphan-warning must NOT fire for resources filtered by argument
# ---------------------------------------------------------------------------


def test_diff_single_resource_does_not_warn_about_other_manifest_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Diffing a single resource must not warn that other manifest entries are
    missing from the server.

    Scenario: manifest has both skills/scribe AND skills/scribe-template; the
    server exposes both.  Running ``omk resource diff skills/scribe-template``
    previously emitted a false-positive warning about skills/scribe because
    server_ids was derived from the *filtered* list (only scribe-template),
    making scribe appear absent.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_current_versions(tmp_path)

    result = runner.invoke(app, ["diff", "skills/scribe-template"])

    assert result.exit_code == 0, result.output
    assert "está no manifest local mas não existe mais no servidor" not in result.output


def test_update_single_resource_does_not_warn_about_other_manifest_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Updating a single resource must not warn that other manifest entries are
    missing from the server.

    Same false-positive as in diff: when update is called with an explicit
    resource argument the filtered server_resources list was used to build
    server_ids, causing every other manifest entry to appear orphaned.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _make_manifest_with_current_versions(tmp_path)

    result = runner.invoke(app, ["update", "skills/scribe-template"])

    assert result.exit_code == 0, result.output
    assert "está no manifest local mas não existe mais no servidor" not in result.output
