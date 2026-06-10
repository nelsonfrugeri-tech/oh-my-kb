"""Tests for ``omk resource list`` and ``omk resource pull``.

Acceptance criteria covered:
- list happy path + ordering
- pull single — happy path, content written, manifest updated
- pull --all — both resources pulled, manifest has both, single top-level pulled_at
- pull --stdout — content on stdout, no file written, no manifest update
- pull (no name, no --all) — error + exit 1
- pull unknown name — error + exit 1
- pull --all with one failure — continues, exit 1
- pull --locale en-US placeholder — stderr warning, file not written, manifest not updated
- pull over existing file — overwrites, action: updated in output
- pull --stdout on binary resource — stderr error, exit 1
- drift check: list_scribe_resources() URIs == RESOURCE_REGISTRY URIs
- manifest round-trip: write -> read -> equal
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from oh_my_harness.kb.cli.app import app
from oh_my_harness.kb.cli.resource.manifest import (
    Manifest,
    ResourceRecord,
    load_manifest,
    save_manifest,
)
from oh_my_harness.kb.cli.resource.registry import RESOURCE_REGISTRY, ResourceMeta
from oh_my_harness.kb.mcp.resources import list_scribe_resources

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_CONTENT = "<!-- content_version: 1 | locale: pt-BR | updated: 2026-01-01 -->\n# Mock"
_PLACEHOLDER = "<!-- placeholder: content not yet translated -->\n# Placeholder"


def _invoke(*args: str, **kwargs: object) -> object:
    return runner.invoke(app, list(args), catch_exceptions=False, **kwargs)


# ---------------------------------------------------------------------------
# Drift check
# ---------------------------------------------------------------------------


def test_registry_uris_match_list_scribe_resources() -> None:
    """RESOURCE_REGISTRY must be in sync with list_scribe_resources()."""
    server_uris = {str(r.uri) for r in list_scribe_resources()}
    registry_uris = {meta.uri for meta in RESOURCE_REGISTRY}
    assert server_uris == registry_uris, (
        f"Drift detected!\n  server: {server_uris}\n  registry: {registry_uris}"
    )


# ---------------------------------------------------------------------------
# Manifest round-trip
# ---------------------------------------------------------------------------


def test_manifest_roundtrip(tmp_path: Path) -> None:
    """save_manifest -> load_manifest produces an equal object."""
    record = ResourceRecord(
        uri="skill://scribe/SKILL.md",
        local_path="~/.claude/skills/scribe/SKILL.md",
        content_version="1",
        pulled_at="2026-01-01T00:00:00Z",
        sha256="abc123",
    )
    m = Manifest(
        pulled_at="2026-01-01T00:00:00Z",
        resources={"skills/scribe": record},
    )
    (tmp_path / ".claude").mkdir()
    save_manifest(m, home=tmp_path)
    loaded = load_manifest(home=tmp_path)
    assert loaded is not None
    assert loaded.pulled_at == m.pulled_at
    assert loaded.resources["skills/scribe"] == record


def test_load_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    """load_manifest returns None when the file does not exist."""
    (tmp_path / ".claude").mkdir()
    result = load_manifest(home=tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# omk resource list
# ---------------------------------------------------------------------------


def test_resource_list_happy_path() -> None:
    """``omk resource list`` exits 0 and prints all resources."""
    result = runner.invoke(app, ["resource", "list"], catch_exceptions=False)
    assert result.exit_code == 0
    output = result.output
    assert "skills/scribe" in output
    assert "template" in output
    assert "skill://scribe/SKILL.md" in output
    assert "skill://scribe/template.md" in output
    assert "~/.claude/skills/scribe/SKILL.md" in output
    assert "~/.claude/template.md" in output


def test_resource_list_ordering() -> None:
    """skills/scribe appears before template (registry order)."""
    result = runner.invoke(app, ["resource", "list"], catch_exceptions=False)
    assert result.exit_code == 0
    idx_skill = result.output.index("skills/scribe")
    idx_tmpl = result.output.index("template")
    assert idx_skill < idx_tmpl


def test_resource_list_count_line() -> None:
    """The count line reflects the registry length."""
    result = runner.invoke(app, ["resource", "list"], catch_exceptions=False)
    count = len(RESOURCE_REGISTRY)
    assert f"{count} resource" in result.output


# ---------------------------------------------------------------------------
# omk resource pull — error cases (no deps on fixtures)
# ---------------------------------------------------------------------------


def test_pull_no_name_no_all_exits_1() -> None:
    """``omk resource pull`` without name or --all exits 1."""
    result = runner.invoke(app, ["resource", "pull"], catch_exceptions=False)
    assert result.exit_code == 1
    assert "provide a resource name or --all" in result.stderr


def test_pull_unknown_name_exits_1() -> None:
    """``omk resource pull unknown`` exits 1 with clear message."""
    result = runner.invoke(app, ["resource", "pull", "does/not/exist"], catch_exceptions=False)
    assert result.exit_code == 1
    assert "unknown resource" in result.stderr


# ---------------------------------------------------------------------------
# omk resource pull — single resource happy path
# ---------------------------------------------------------------------------


def test_pull_single_happy_path(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """Pull a single resource: file is written, exit 0."""
    result = runner.invoke(app, ["resource", "pull", "skills/scribe"], catch_exceptions=False)
    assert result.exit_code == 0
    dest = fake_claude_home / ".claude" / "skills" / "scribe" / "SKILL.md"
    assert dest.is_file()


def test_pull_single_content_matches(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """Pulled file content matches what read_scribe_resource returns."""
    runner.invoke(app, ["resource", "pull", "skills/scribe"], catch_exceptions=False)
    dest = fake_claude_home / ".claude" / "skills" / "scribe" / "SKILL.md"
    written = dest.read_text(encoding="utf-8")
    assert "content_version: 1" in written
    assert "# Mock" in written


def test_pull_single_manifest_entry_written(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """After pull, manifest contains the pulled resource."""
    runner.invoke(app, ["resource", "pull", "skills/scribe"], catch_exceptions=False)
    m = load_manifest(home=fake_claude_home)
    assert m is not None
    assert "skills/scribe" in m.resources
    rec = m.resources["skills/scribe"]
    assert rec.content_version == "1"
    expected_sha = hashlib.sha256(_MOCK_CONTENT.encode("utf-8")).hexdigest()
    assert rec.sha256 == expected_sha


def test_pull_over_existing_file_shows_updated(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """Pulling over an existing file shows 'action: updated'."""
    # First pull
    runner.invoke(app, ["resource", "pull", "skills/scribe"], catch_exceptions=False)
    # Second pull
    result = runner.invoke(app, ["resource", "pull", "skills/scribe"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "updated" in result.output


def test_pull_manifest_pulled_at_updated_on_second_pull(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """On the second pull, manifest pulled_at is refreshed."""
    runner.invoke(app, ["resource", "pull", "skills/scribe"], catch_exceptions=False)
    first = load_manifest(home=fake_claude_home)
    assert first is not None
    first_ts = first.resources["skills/scribe"].pulled_at

    runner.invoke(app, ["resource", "pull", "skills/scribe"], catch_exceptions=False)
    second = load_manifest(home=fake_claude_home)
    assert second is not None
    second_ts = second.resources["skills/scribe"].pulled_at
    # Timestamps should be equal or later (same second is fine)
    assert second_ts >= first_ts


# ---------------------------------------------------------------------------
# omk resource pull --all
# ---------------------------------------------------------------------------


def test_pull_all_pulls_both_resources(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """``pull --all`` writes both resources to disk."""
    result = runner.invoke(app, ["resource", "pull", "--all"], catch_exceptions=False)
    assert result.exit_code == 0
    skill = fake_claude_home / ".claude" / "skills" / "scribe" / "SKILL.md"
    tmpl = fake_claude_home / ".claude" / "template.md"
    assert skill.is_file()
    assert tmpl.is_file()


def test_pull_all_manifest_has_both_entries(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """After ``pull --all``, manifest contains entries for every resource."""
    runner.invoke(app, ["resource", "pull", "--all"], catch_exceptions=False)
    m = load_manifest(home=fake_claude_home)
    assert m is not None
    for meta in RESOURCE_REGISTRY:
        assert meta.short_id in m.resources


def test_pull_all_single_top_level_pulled_at(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """``pull --all`` produces a single top-level pulled_at in the manifest."""
    runner.invoke(app, ["resource", "pull", "--all"], catch_exceptions=False)
    m = load_manifest(home=fake_claude_home)
    assert m is not None
    assert m.pulled_at  # non-empty
    # All per-resource pulled_at should equal top-level pulled_at
    for rec in m.resources.values():
        assert rec.pulled_at == m.pulled_at


# ---------------------------------------------------------------------------
# omk resource pull --stdout
# ---------------------------------------------------------------------------


def test_pull_stdout_content_on_stdout(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """``pull --stdout`` prints content to stdout."""
    result = runner.invoke(
        app, ["resource", "pull", "skills/scribe", "--stdout"], catch_exceptions=False
    )
    assert result.exit_code == 0
    assert "# Mock" in result.output


def test_pull_stdout_no_file_written(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """``pull --stdout`` does NOT write the resource to disk."""
    runner.invoke(app, ["resource", "pull", "skills/scribe", "--stdout"], catch_exceptions=False)
    dest = fake_claude_home / ".claude" / "skills" / "scribe" / "SKILL.md"
    assert not dest.exists()


def test_pull_stdout_no_manifest_update(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
) -> None:
    """``pull --stdout`` does NOT update the manifest."""
    runner.invoke(app, ["resource", "pull", "skills/scribe", "--stdout"], catch_exceptions=False)
    m = load_manifest(home=fake_claude_home)
    assert m is None


# ---------------------------------------------------------------------------
# omk resource pull --locale en-US placeholder
# ---------------------------------------------------------------------------


def test_pull_placeholder_locale_no_file_written(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Placeholder content is not written to disk."""

    def _placeholder_read(uri: str, locale: str = "pt-BR") -> str:
        if locale == "en-US":
            return _PLACEHOLDER
        return _MOCK_CONTENT

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _placeholder_read)

    result = runner.invoke(
        app,
        ["resource", "pull", "skills/scribe", "--locale", "en-US"],
        catch_exceptions=False,
    )
    # exit code 1 because placeholder was detected
    assert result.exit_code == 1
    dest = fake_claude_home / ".claude" / "skills" / "scribe" / "SKILL.md"
    assert not dest.exists()


def test_pull_placeholder_locale_stderr_warning(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Placeholder content triggers a stderr warning."""

    def _placeholder_read(uri: str, locale: str = "pt-BR") -> str:
        return _PLACEHOLDER

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _placeholder_read)

    result = runner.invoke(
        app,
        ["resource", "pull", "skills/scribe", "--locale", "en-US"],
        catch_exceptions=False,
    )
    assert "placeholder" in result.stderr.lower() or "warning" in result.stderr.lower()


def test_pull_placeholder_manifest_not_updated(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Placeholder content does not update the manifest."""

    def _placeholder_read(uri: str, locale: str = "pt-BR") -> str:
        return _PLACEHOLDER

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _placeholder_read)

    runner.invoke(
        app,
        ["resource", "pull", "skills/scribe", "--locale", "en-US"],
        catch_exceptions=False,
    )
    m = load_manifest(home=fake_claude_home)
    assert m is None


# ---------------------------------------------------------------------------
# omk resource pull --all with one failure
# ---------------------------------------------------------------------------


def test_pull_all_continues_on_failure_exits_1(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pull --all`` continues when one resource fails; exits 1."""
    failed_uris: list[str] = []
    succeeded_uris: list[str] = []

    def _failing_read(uri: str, locale: str = "pt-BR") -> str:
        if not failed_uris:
            failed_uris.append(uri)
            raise FileNotFoundError("intentional failure")
        succeeded_uris.append(uri)
        return _MOCK_CONTENT

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _failing_read)

    result = runner.invoke(app, ["resource", "pull", "--all"], catch_exceptions=False)
    # One failed, at least one succeeded — all resources attempted
    assert len(failed_uris) == 1
    assert len(succeeded_uris) >= 1
    assert result.exit_code == 1


def test_pull_all_reports_per_resource_on_partial_failure(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-resource failure summary appears in stderr."""
    first_call = True

    def _failing_read(uri: str, locale: str = "pt-BR") -> str:
        nonlocal first_call
        if first_call:
            first_call = False
            raise FileNotFoundError("intentional failure")
        return _MOCK_CONTENT

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _failing_read)

    result = runner.invoke(app, ["resource", "pull", "--all"], catch_exceptions=False)
    assert "FAILED" in result.stderr


# ---------------------------------------------------------------------------
# omk resource pull --stdout on binary resource
# ---------------------------------------------------------------------------


def test_pull_stdout_binary_resource_exits_1(
    fake_claude_home: Path,
    mock_read_resource: Callable[[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pull --stdout`` on a binary resource exits 1 with error on stderr."""
    import sys

    # Ensure the module is imported so sys.modules has it
    import oh_my_harness.kb.cli.resource  # noqa: F401

    _pull_mod = sys.modules["oh_my_harness.kb.cli.resource.pull_cmd"]
    _registry_mod = sys.modules["oh_my_harness.kb.cli.resource.registry"]

    fake_binary = ResourceMeta(
        short_id="skills/scribe",
        uri="skill://scribe/SKILL.md",
        local_path="~/.claude/skills/scribe/SKILL.md",
        mime_type="image/png",
    )
    monkeypatch.setattr(_pull_mod, "RESOURCE_REGISTRY", [fake_binary])
    monkeypatch.setattr(_registry_mod, "RESOURCE_REGISTRY", [fake_binary])

    result = runner.invoke(
        app,
        ["resource", "pull", "skills/scribe", "--stdout"],
        catch_exceptions=False,
    )
    assert result.exit_code == 1
    assert "binary" in result.stderr.lower()


# ---------------------------------------------------------------------------
# omk resource pull --locale (default locale works)
# ---------------------------------------------------------------------------


def test_pull_locale_flag_passes_through(
    fake_claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--locale`` flag is forwarded to read_scribe_resource."""
    received_locales: list[str] = []

    def _tracking_read(uri: str, locale: str = "pt-BR") -> str:
        received_locales.append(locale)
        return _MOCK_CONTENT

    monkeypatch.setattr("oh_my_harness.kb.mcp.resources.read_scribe_resource", _tracking_read)

    runner.invoke(
        app,
        ["resource", "pull", "skills/scribe", "--locale", "en-US"],
        catch_exceptions=False,
    )
    assert "en-US" in received_locales
