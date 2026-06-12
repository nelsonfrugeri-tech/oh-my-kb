"""Agent bootstrap rules template — static loader and dynamic block generator."""

from __future__ import annotations

from pathlib import Path

from oh_my_harness.kb.cli._remote import MANIFEST_URL, REPO_URL
from oh_my_harness.kb.i18n import DEFAULT_LOCALE, resolve_locale_path

_AGENTS_DIR: Path = Path(__file__).parent
_RULES_FILENAME: str = "rules_template.md"


def load_template(locale: str = DEFAULT_LOCALE) -> str:
    """Return the raw rules_template.md for the requested locale, with fallback."""
    path = resolve_locale_path(_AGENTS_DIR, _RULES_FILENAME, locale=locale)
    return path.read_text(encoding="utf-8")


def render_rules(universe: str, locale: str = DEFAULT_LOCALE) -> str:
    """Return bootstrap rules with ``{universe}``, ``{repo_url}``, ``{manifest_url}``."""
    return (
        load_template(locale=locale)
        .replace("{universe}", universe)
        .replace("{repo_url}", REPO_URL)
        .replace("{manifest_url}", MANIFEST_URL)
    )


def render_dynamic_block(universe: str) -> str:
    """Generate the full rules block dynamically from the MCP registry.

    1. Imports the 5 core kb tool objects directly.
    2. Renders one bullet per tool.
    3. Adds skills/agents management hint with manifest URL.
    """
    from oh_my_harness.kb.agents.harness import TOOL_TRIGGERS
    from oh_my_harness.kb.mcp.tools import (
        KB_EXPAND_TOOL,
        KB_RECENT_TOOL,
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
    ]

    lines: list[str] = [
        f"## oh-my-harness — Base de Conhecimento (universe: {universe})",
        "",
        "### Tools disponíveis",
        "",
    ]

    for tool in tools:
        trigger = TOOL_TRIGGERS.get(tool.name)
        if trigger is None:
            raw_desc: str = tool.description or ""
            trigger = raw_desc[:120].rstrip() + ("..." if len(raw_desc) > 120 else "")
            trigger += "  # (no trigger configured — using tool description)"
        lines.append(f"- `{tool.name}` — {trigger}")

    lines += [
        "",
        "### Skills e agents",
        "",
        "Skills instalados em `~/.claude/skills/<nome>/SKILL.md`,"
        " agents em `~/.claude/agents/<nome>.md`.",
        "Para gerenciar: `omh skills pull|diff|update` e `omh agents pull|diff|update`.",
        f"Manifest oficial: {MANIFEST_URL}",
        f"Repositório: {REPO_URL}",
        "",
        "### Regras gerais",
        "",
        "- Sempre use o universe ativo configurado em KB_UNIVERSE.",
        "- Prefira kb_search para recuperação;"
        " use kb_tree quando o usuário precisar de orientação.",
    ]

    # ── Agentes pessoais (o-agents-mcp) ──
    from oh_my_harness.agents.mcp.tools import DEVELOP_LEAP_UPDATE_TOOL
    from oh_my_harness.agents.triggers import AGENTS_TOOL_TRIGGERS

    agent_tools = [DEVELOP_LEAP_UPDATE_TOOL]

    lines += [
        "",
        "## Agentes pessoais (o-agents-mcp)",
        "",
    ]
    for tool in agent_tools:
        trigger = AGENTS_TOOL_TRIGGERS.get(tool.name, tool.description or tool.name)
        lines.append(f"- `{tool.name}` — {trigger}")

    return "\n".join(lines)
