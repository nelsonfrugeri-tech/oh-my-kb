"""Static MCP resources served by ``o-kb-mcp``.

The scribe skill (``skill://scribe/SKILL.md``) and its body template
(``skill://scribe/template.md``) are served from disk **on every request**
so editing the file shows up on the next read without restarting the
server. The disk files live next to this module under ``skills/scribe/<locale>/``,
so the package install is the unit of distribution and the running server is
the unit of editing.
"""

from __future__ import annotations

from pathlib import Path

from mcp.types import Resource

from oh_my_harness.kb.i18n import DEFAULT_LOCALE, resolve_locale_path

SKILLS_DIR = Path(__file__).parent / "skills"
SCRIBE_DIR = SKILLS_DIR / "scribe"

SCRIBE_SKILL_URI = "skill://scribe/SKILL.md"
SCRIBE_TEMPLATE_URI = "skill://scribe/template.md"

_URI_TO_FILENAME: dict[str, str] = {
    SCRIBE_SKILL_URI: "SKILL.md",
    SCRIBE_TEMPLATE_URI: "template.md",
}

SHORT_ID_TO_URI: dict[str, str] = {
    "skills/scribe": SCRIBE_SKILL_URI,
    "template": SCRIBE_TEMPLATE_URI,
}


def list_scribe_resources() -> list[Resource]:
    """Return the static catalog of scribe resources."""
    return [
        Resource(
            uri=SCRIBE_SKILL_URI,  # type: ignore[arg-type]
            name="scribe",
            title="Scribe skill",
            description=(
                "Playbook for writing well-formed notes via kb_write — type "
                "decision, summary as dense prose, entity extraction, "
                "links via kb_search. Read once per kb_write call until "
                "o-kb-agents automates it."
            ),
            mimeType="text/markdown",
        ),
        Resource(
            uri=SCRIBE_TEMPLATE_URI,  # type: ignore[arg-type]
            name="scribe-template",
            title="Scribe — note body template",
            description=(
                "Required structure of the note body, with per-type "
                "sections. The summary is separate prose, not part of "
                "this template."
            ),
            mimeType="text/markdown",
        ),
    ]


def read_scribe_resource(uri: str, locale: str = DEFAULT_LOCALE) -> str:
    """Return the markdown content of the resource at ``uri`` for ``locale``.

    Reads the disk file each call — edits to the markdown reflect on the
    next read without a server restart.

    ``locale`` defaults to ``DEFAULT_LOCALE``; the MCP server call site passes
    no locale so existing ``read_scribe_resource(uri)`` callers are unaffected.
    """
    filename = _URI_TO_FILENAME.get(uri)
    if filename is None:
        raise ValueError(f"unknown resource uri: {uri!r}")
    return resolve_locale_path(SCRIBE_DIR, filename, locale).read_text(encoding="utf-8")
