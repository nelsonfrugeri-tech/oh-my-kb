"""Resource handlers — `skill://scribe/SKILL.md` and template.

We test the resources module directly (it's where the disk read happens)
and verify the wiring at the Server level by calling the same list/read
helpers the SDK calls behind the decorator.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from oh_my_kb.mcp import resources as resources_module
from oh_my_kb.mcp.resources import (
    SCRIBE_SKILL_URI,
    SCRIBE_TEMPLATE_URI,
    SKILLS_DIR,
    list_scribe_resources,
    read_scribe_resource,
)


def test_list_includes_both_scribe_resources() -> None:
    resources = list_scribe_resources()
    uris = {str(r.uri) for r in resources}
    assert SCRIBE_SKILL_URI in uris
    assert SCRIBE_TEMPLATE_URI in uris


def test_resources_carry_useful_metadata() -> None:
    resources = list_scribe_resources()
    by_uri = {str(r.uri): r for r in resources}
    skill = by_uri[SCRIBE_SKILL_URI]
    template = by_uri[SCRIBE_TEMPLATE_URI]

    assert skill.mimeType == "text/markdown"
    assert template.mimeType == "text/markdown"
    assert skill.description and "kb_write" in skill.description
    assert template.description and "template" in template.description.lower()


def test_read_skill_returns_file_content() -> None:
    text = read_scribe_resource(SCRIBE_SKILL_URI)
    # Sanity check: must mention the major sections the spec requires.
    assert "Scribe" in text
    assert "summary" in text
    assert "type" in text
    assert "kb_search" in text
    assert "template" in text


def test_read_template_returns_file_content() -> None:
    text = read_scribe_resource(SCRIBE_TEMPLATE_URI)
    assert "template" in text.lower()
    assert "decision" in text.lower()
    assert "summary" in text.lower()


def test_read_unknown_uri_raises() -> None:
    with pytest.raises(ValueError):
        read_scribe_resource("skill://does/not/exist.md")


def test_edits_to_disk_reflect_on_re_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resources are read from disk **on every call** so edits show up live."""
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "SKILL.md"
        fake.write_text("version-one", encoding="utf-8")
        monkeypatch.setitem(resources_module._URI_TO_PATH, SCRIBE_SKILL_URI, fake)

        assert read_scribe_resource(SCRIBE_SKILL_URI) == "version-one"

        fake.write_text("version-two", encoding="utf-8")
        assert read_scribe_resource(SCRIBE_SKILL_URI) == "version-two"


def test_skill_and_template_files_exist_in_package() -> None:
    assert (SKILLS_DIR / "scribe" / "SKILL.md").is_file()
    assert (SKILLS_DIR / "scribe" / "template.md").is_file()
