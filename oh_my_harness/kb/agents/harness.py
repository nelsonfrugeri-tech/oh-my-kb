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
# understand when to invoke each tool.  If a tool is not listed here, the
# block renderer falls back to the tool's own description field.
TOOL_TRIGGERS: dict[str, str] = {
    "kb_write": (
        "Use quando o usuário pedir para salvar, registrar ou documentar algo"
    ),
    "kb_search": (
        "Use quando o usuário pedir para buscar, encontrar ou lembrar algo"
    ),
    "kb_tree": (
        "Use quando o usuário pedir uma visão geral, mapa ou estrutura do conhecimento"
    ),
    "kb_expand": (
        "Use quando o usuário quiser aprofundar, ler na íntegra ou seguir links de uma nota"
    ),
    "kb_recent": (
        "Use quando o usuário pedir as últimas notas, histórico recente ou novidades de um projeto"
    ),
    "kb_resource_list": (
        "Use quando o usuário perguntar quais skills tem instaladas,"
        " se os resources estão atualizados ou quiser listar o que o oh-my-kb tem disponível"
    ),
    "kb_resource_diff": (
        "Use quando o usuário quiser saber o que mudou nas skills,"
        " se tem algo novo no oh-my-kb ou pedir para mostrar o diff dos resources"
    ),
    "kb_resource_update": (
        "Use quando o usuário pedir para atualizar as skills do oh-my-kb,"
        " quiser a versão mais recente dos resources, atualizar o template de nota"
        " ou sincronizar os resources"
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
