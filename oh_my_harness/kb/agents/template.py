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


def render_rules(kb_name: str, locale: str = DEFAULT_LOCALE) -> str:
    """Return bootstrap rules with ``{kb_name}``, ``{repo_url}``, ``{manifest_url}``."""
    return (
        load_template(locale=locale)
        .replace("{kb_name}", kb_name)
        # Support old templates that still use {universe}.
        .replace("{universe}", kb_name)
        .replace("{repo_url}", REPO_URL)
        .replace("{manifest_url}", MANIFEST_URL)
    )


def render_dynamic_block(kb_name: str) -> str:
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
        f"## oh-my-harness — modular AI harness (knowledge base: {kb_name})",
        "",
        "oh-my-harness is a modular AI harness. Current modules:",
        "- **kb** — knowledge base via MCP (tools below)",
        "- **agents** — personal agents via MCP",
        "",
        "The `omh` CLI orchestrates everything: `omh kb`, `omh skills`, `omh agents`.",
        "",
        "### Comportamento agentic — obrigatório",
        "",
        "Você é um agente. Use as tools de kb-mcp **por iniciativa semântica**,"
        " não apenas quando o usuário pedir explicitamente. As regras abaixo são vinculantes.",
        "",
        "**Buscar (kb_search) — quando agir sem pedido:**",
        "- O usuário menciona algo do passado, uma decisão prévia, um procedimento estabelecido,"
        " uma funcionalidade conhecida, ou uma ferramenta usada antes.",
        "- Surge um tema/conceito/sigla que você não conhece a partir do contexto atual.",
        "- Você está prestes a responder algo sobre o projeto/usuário sem confirmar se já"
        " existe nota sobre o assunto.",
        "- Em qualquer dúvida: busque primeiro. Buscar é barato; ignorar memória existente"
        " quebra a continuidade.",
        "",
        "**Escrever (kb_write) — quando agir sem pedido:**",
        "- Foi tomada uma decisão (arquitetural, técnica, de processo).",
        "- Foi estabelecido um procedimento, convenção ou padrão novo.",
        "- Aconteceu um evento relevante (incidente, marco, mudança de estado).",
        "- Foi descoberta uma referência útil (link, doc, padrão externo).",
        "- Foi aprendido um fato novo sobre o usuário ou suas preferências.",
        "- Qualquer NOVO conhecimento sobre o projeto que terá valor em sessões futuras.",
        "",
        "**Regra rígida de execução de kb_write — SEM EXCEÇÃO:**",
        "NUNCA chame kb_write de forma síncrona no loop principal."
        " SEMPRE delegue a escrita para um sub-agent do harness ativo"
        " (no claude-code: ferramenta Task/Agent).",
        "Razões: (a) escrita exige seguir o skill `scribe` integralmente —"
        " passos demais para o loop principal;"
        " (b) não pode bloquear a conversa em andamento;"
        " (c) escrita assíncrona em sub-agent mantém o agente principal focado"
        " em responder o usuário.",
        "",
        "**Navegar (kb_tree + kb_expand) — quando agir sem pedido:**",
        "- Antes de buscar em uma knowledge base grande, peça `kb_tree` para se orientar.",
        "- Após uma busca promissora, abra com `kb_expand` e siga `links_out`.",
        "",
        "**Recall temporal (kb_recent) — quando agir sem pedido:**",
        "- A pergunta tem dimensão temporal (\"o que mudou\", \"última vez que\","
        " \"recente\", \"novidades\", \"o que aconteceu\").",
        "",
        "Pedidos explícitos do usuário (\"busque X\", \"registre Y\","
        " \"atualize a nota Z\") também disparam a tool correspondente."
        " A iniciativa, porém, não fica só com o usuário — você é quem detecta os sinais.",
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
        "- A knowledge base ativa está configurada via KB_NAME.",
        "- Antes de cada `kb_write`, leia `~/.claude/skills/scribe/SKILL.md` e"
        " `~/.claude/skills/scribe/template.md` — o sub-agent que executa a escrita"
        " precisa seguir o processo do scribe (escolha de tipo, summary denso,"
        " entidades, links).",
        "- Para atualizar uma nota existente: encontre-a com `kb_search`, depois passe"
        " seu UUID em `supersedes` na chamada de `kb_write`.",
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
