"""Agent bootstrap rules template — static loader and dynamic block generator."""

from __future__ import annotations

from pathlib import Path

from oh_my_harness.kb.i18n import DEFAULT_LOCALE, resolve_locale_path

_AGENTS_DIR: Path = Path(__file__).parent
_RULES_FILENAME: str = "rules_template.md"


def load_template(locale: str = DEFAULT_LOCALE) -> str:
    """Return the raw rules_template.md for the requested locale, with fallback."""
    path = resolve_locale_path(_AGENTS_DIR, _RULES_FILENAME, locale=locale)
    return path.read_text(encoding="utf-8")


def render_rules(universe: str, locale: str = DEFAULT_LOCALE) -> str:
    """Return the bootstrap rules with ``{universe}`` substituted."""
    return load_template(locale=locale).replace("{universe}", universe)


def render_dynamic_block(universe: str) -> str:
    """Generate the full rules block dynamically from the MCP registry.

    Instead of a static template, this function:
    1. Imports the tool objects directly from ``oh_my_harness.kb.mcp.tools`` (no server
       spin-up needed — they are statically importable Python objects).
    2. Calls ``list_scribe_resources()`` to get the current resource list.
    3. Renders one bullet per tool (using ``TOOL_TRIGGERS`` for the human-readable
       trigger phrase, falling back to the tool description if no trigger exists).
    4. Renders one bullet per resource.

    The result is injected between the sentinel markers by :func:`inject_block`.
    """
    from oh_my_harness.kb.agents.harness import TOOL_TRIGGERS
    from oh_my_harness.kb.mcp.resources import list_scribe_resources
    from oh_my_harness.kb.mcp.tools import (
        KB_EXPAND_TOOL,
        KB_RECENT_TOOL,
        KB_RESOURCE_DIFF_TOOL,
        KB_RESOURCE_LIST_TOOL,
        KB_RESOURCE_UPDATE_TOOL,
        KB_SEARCH_TOOL,
        KB_TREE_TOOL,
        KB_WRITE_TOOL,
    )

    tools = [
        KB_WRITE_TOOL,
        KB_SEARCH_TOOL,
        KB_TREE_TOOL,
        KB_EXPAND_TOOL,
        KB_RECENT_TOOL,
        KB_RESOURCE_LIST_TOOL,
        KB_RESOURCE_DIFF_TOOL,
        KB_RESOURCE_UPDATE_TOOL,
    ]
    resources = list_scribe_resources()

    lines: list[str] = [
        f"## oh-my-harness — Base de Conhecimento (universe: {universe})",
        "",
        "### Tools disponíveis",
        "",
    ]

    for tool in tools:
        trigger = TOOL_TRIGGERS.get(tool.name)
        if trigger is None:
            # Fallback: use the tool description (trimmed to 120 chars to avoid verbosity)
            raw_desc: str = tool.description or ""
            trigger = raw_desc[:120].rstrip() + ("..." if len(raw_desc) > 120 else "")
            trigger += "  # (no trigger configured — using tool description)"
        lines.append(f"- `{tool.name}` — {trigger}")

    lines += [
        "",
        "### Resources disponíveis",
        "",
    ]

    for resource in resources:
        lines.append(f"- `{resource.uri}` — {resource.description or resource.name}")

    lines += [
        "",
        "### Regras gerais",
        "",
        "- Sempre use o universe ativo configurado em KB_UNIVERSE.",
        "- Leia skill://scribe/SKILL.md antes de qualquer kb_write.",
        "- Prefira kb_search para recuperação;"
        " use kb_tree quando o usuário precisar de orientação.",
    ]

    return "\n".join(lines)
