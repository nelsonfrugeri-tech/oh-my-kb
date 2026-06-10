"""Resource registry — single source of truth for all MCP resources.

Every resource that ``omk resource`` commands manage must have an entry here.
Adding a new resource requires only a new ``ResourceMeta`` in ``RESOURCE_REGISTRY``;
all list/pull/diff/update commands consume this registry automatically.

MCP server availability is not required; resources are resolved directly
from the installed package.
"""

from __future__ import annotations

from dataclasses import dataclass

from oh_my_harness.kb.mcp.resources import SCRIBE_SKILL_URI, SCRIBE_TEMPLATE_URI


@dataclass(frozen=True)
class ResourceMeta:
    """Static metadata for a single MCP resource.

    Attributes:
        short_id:   Human-readable identifier used in CLI commands
                    (e.g. ``skills/scribe`` or ``template``).
        uri:        Full MCP resource URI (e.g. ``skill://scribe/SKILL.md``).
        local_path: Tilde-literal destination path under ``~/.claude/``.
                    Expand with ``Path(local_path).expanduser()`` at write-time.
        mime_type:  MIME type of the resource content.  Checked before
                    ``--stdout`` to guard against binary content.
    """

    short_id: str
    uri: str
    local_path: str
    mime_type: str = "text/markdown"


RESOURCE_REGISTRY: list[ResourceMeta] = [
    ResourceMeta(
        short_id="skills/scribe",
        uri=SCRIBE_SKILL_URI,
        local_path="~/.claude/skills/scribe/SKILL.md",
        mime_type="text/markdown",
    ),
    ResourceMeta(
        short_id="template",
        uri=SCRIBE_TEMPLATE_URI,
        local_path="~/.claude/template.md",
        mime_type="text/markdown",
    ),
]
