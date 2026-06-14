"""Harness registry — maps harness names to their target file and detection signal."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class Harness:
    name: str
    target_filename: str
    detection_signal: str | None
    scope: Literal["global", "project"] = "project"
    display_label: str = ""
    display_path: str = ""


HARNESS_REGISTRY: dict[str, Harness] = {
    "claude-code": Harness(
        "claude-code",
        "CLAUDE.md",
        ".claude",
        scope="global",
        display_label="Claude Code CLI",
        display_path="~/.claude/CLAUDE.md",
    ),
    "claude-desktop": Harness(
        "claude-desktop",
        "CLAUDE.md",
        None,
        scope="project",
        display_label="Claude Desktop",
        display_path="(project-local CLAUDE.md)",
    ),
}

# Selectable harnesses in install order — only "claude-code" is implemented;
# the rest are "coming soon" placeholders for the UI.
HARNESS_COMING_SOON: list[str] = ["claude-desktop", "cursor", "copilot"]

# Natural-language trigger phrases for each tool name.
# These appear in the generated ~/.claude/CLAUDE.md block so the harness can
# understand when to invoke each tool.  Each phrase is **agentic-first**: the
# harness should decide to call the tool from semantic signals in the
# conversation, not wait for an explicit user request (user requests also
# trigger, but they are not the only trigger).
TOOL_TRIGGERS: dict[str, str] = {
    "kb_write": (
        "Use proativamente sempre que surgir conhecimento NOVO sobre o projeto ou usuário "
        "(decisão tomada, procedimento estabelecido, evento ocorrido, referência útil, "
        "padrão descoberto, fato sobre o usuário, algo criado/alterado significativamente). "
        "REGRA RÍGIDA: NUNCA chame esta tool de forma síncrona no loop principal — "
        "SEMPRE delegue a escrita para um sub-agent (Task/Agent). Também execute "
        "quando o usuário pedir explicitamente"
    ),
    "kb_search": (
        "Use proativamente sempre que detectar referência semântica ao passado, a um "
        "procedimento, a uma funcionalidade, a uma ferramenta usada antes, a uma decisão "
        "anterior, ou a qualquer assunto que não esteja claro no contexto atual da sessão. "
        "Em dúvida, busque — é barato; ignorar memória existente quebra continuidade. "
        "Também execute quando o usuário pedir explicitamente"
    ),
    "kb_tree": (
        "Use para se orientar antes de buscar em uma knowledge base grande, ou quando "
        "a pergunta for estrutural (\"o que existe?\", \"quais tópicos esse projeto cobre?\"). "
        "Também execute quando o usuário pedir um mapa do conhecimento"
    ),
    "kb_expand": (
        "Use para ler uma nota completa e seguir seus links — quando uma busca retornou "
        "um resultado promissor que merece aprofundamento, ou para navegar o grafo via "
        "links_out. Também execute quando o usuário pedir os detalhes de uma nota"
    ),
    "kb_recent": (
        "Use quando a pergunta tiver dimensão temporal explícita ou implícita "
        "(\"últimas decisões\", \"o que mudou\", \"o que aconteceu recentemente\") ou "
        "quando precisar do histórico recente para situar uma resposta. Também "
        "execute quando o usuário pedir últimas notas/novidades"
    ),
}


class UnknownHarnessError(ValueError):
    """Raised when harness name is not in HARNESS_REGISTRY."""


def resolve_harness(name: str) -> Harness:
    """Return the :class:`Harness` for *name*, raising :class:`UnknownHarnessError` if absent."""
    try:
        return HARNESS_REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(HARNESS_REGISTRY))
        raise UnknownHarnessError(f"unknown harness '{name}'; known: {known}") from None


def target_path_for(harness: Harness, project_path: Path) -> Path:
    """Return the absolute path to the harness rules file.

    For *global* harnesses (scope='global'), the path is always resolved relative
    to the user's home directory regardless of *project_path*.  For *project*
    harnesses the file lives under *project_path*.
    """
    if harness.scope == "global":
        # Global harnesses always resolve to ~/.claude/<target_filename>
        # (or the appropriate global config directory based on detection_signal).
        if harness.detection_signal:
            return Path.home() / harness.detection_signal / harness.target_filename
        return Path.home() / harness.target_filename
    return project_path / harness.target_filename
