"""Static MCP resources served by ``o-kb-mcp``.

The scribe skill (``skill://scribe/SKILL.md``) and its body template
(``skill://scribe/template.md``) are served from disk **on every request**
so editing the file shows up on the next read without restarting the
server. The disk files live next to this module under ``skills/``, so the
package install is the unit of distribution and the running server is the
unit of editing.
"""

from __future__ import annotations

from pathlib import Path

from mcp.types import Resource

SKILLS_DIR = Path(__file__).parent / "skills"

SCRIBE_SKILL_URI = "skill://scribe/SKILL.md"
SCRIBE_TEMPLATE_URI = "skill://scribe/template.md"

_URI_TO_PATH: dict[str, Path] = {
    SCRIBE_SKILL_URI: SKILLS_DIR / "scribe" / "SKILL.md",
    SCRIBE_TEMPLATE_URI: SKILLS_DIR / "scribe" / "template.md",
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


def read_scribe_resource(uri: str) -> str:
    """Return the markdown content of the resource at ``uri``.

    Reads the disk file each call — edits to the markdown reflect on the
    next read without a server restart.
    """
    path = _URI_TO_PATH.get(uri)
    if path is None:
        raise ValueError(f"unknown resource uri: {uri!r}")
    return path.read_text(encoding="utf-8")
