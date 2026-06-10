import pytest

from oh_my_harness.kb.mcp.resources import (
    SCRIBE_SKILL_URI,
    SCRIBE_TEMPLATE_URI,
    read_scribe_resource,
)


def test_read_scribe_skill_returns_pt_br():
    content = read_scribe_resource(SCRIBE_SKILL_URI)
    assert "pt-BR" in content  # content_version marker


def test_read_scribe_template_returns_pt_br():
    content = read_scribe_resource(SCRIBE_TEMPLATE_URI)
    assert "pt-BR" in content


def test_read_scribe_resource_unknown_uri():
    with pytest.raises(ValueError, match="unknown resource uri"):
        read_scribe_resource("skill://unknown/file.md")


def test_read_scribe_resource_fallback_on_missing_locale(tmp_path, monkeypatch):
    """Requesting a locale with no file falls back to pt-BR."""
    import oh_my_harness.kb.mcp.resources as resources_mod
    monkeypatch.setattr(resources_mod, "SCRIBE_DIR", tmp_path / "scribe")
    (tmp_path / "scribe" / "pt-BR").mkdir(parents=True)
    (tmp_path / "scribe" / "pt-BR" / "SKILL.md").write_text("pt-BR fallback")
    content = read_scribe_resource(SCRIBE_SKILL_URI, locale="xx-XX")
    assert content == "pt-BR fallback"
