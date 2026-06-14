"""Interactive setup wizard for ``omk install``.

Collects user configuration choices through a sequential prompt UI.
Every step shows a default that is accepted by pressing Enter.
``--yes`` (``non_interactive=True``) accepts all defaults without prompting.

Architecture
------------
:class:`WizardStep` — describes one question (id, prompt, default, validator).
:class:`Wizard` — runs the steps and returns :class:`InstallChoices`.
:class:`InstallChoices` — typed dataclass with the collected decisions.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WizardStep:
    """One question in the wizard flow.

    Attributes:
        id: Unique identifier — used as a key in the prefill dict.
        prompt: Human-readable question shown to the user.
        default: Value used when the user presses Enter (or ``--yes``).
        validator: Optional callable that validates / coerces the raw string
            input.  Receives the raw string; should return the coerced value
            or raise :class:`ValueError` for invalid input.
        applies_to_summary: Whether to include this step in the summary table.
    """

    id: str
    prompt: str
    default: Any
    validator: Callable[[Any], Any] | None = None
    applies_to_summary: bool = True


def _validate_path(raw: Any) -> Path:
    """Expand ``~`` and return a :class:`Path`."""
    return Path(str(raw)).expanduser()


def _validate_port(raw: Any) -> int:
    """Return an integer port number in [1, 65535]."""
    try:
        port = int(str(raw))
    except ValueError:
        raise ValueError(f"port must be an integer, got: {raw!r}") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"port must be between 1 and 65535, got: {port}")
    return port


def _validate_kb_name(raw: Any) -> str:
    """Return a stripped non-empty knowledge base name."""
    name = str(raw).strip()
    if not name:
        raise ValueError("knowledge base name cannot be empty")
    return name


# Backward-compatible alias used by existing tests that import _validate_universe.
_validate_universe = _validate_kb_name


def _validate_bool(raw: Any) -> bool:
    """Accept y/n/sim/nao (and their booleans) and return a bool."""
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in {"y", "yes", "s", "sim", "true", "1"}:
        return True
    if s in {"n", "no", "nao", "não", "false", "0"}:
        return False
    raise ValueError(f"answer must be y/n, got: {raw!r}")


def _display_default(value: Any) -> str:
    """Render a step default for display in prompts ("s"/"n" for bools)."""
    if value is True:
        return "s"
    if value is False:
        return "n"
    return str(value)


def _validate_harness(raw: Any) -> str:
    """Accept only selectable harnesses."""
    from oh_my_harness.kb.agents.harness import HARNESS_COMING_SOON, HARNESS_REGISTRY

    name = str(raw).strip().lower()
    # Check coming-soon first — these may not be in HARNESS_REGISTRY yet.
    if name in HARNESS_COMING_SOON:
        raise ValueError(f"harness '{name}' is not yet available")
    if name not in HARNESS_REGISTRY:
        known = ", ".join(sorted(HARNESS_REGISTRY))
        raise ValueError(f"unknown harness '{name}'; known: {known}")
    return name


# Default step definitions (used by the wizard unless overridden).
#
# Step order is intentional: ask which harness to configure FIRST (it scopes the
# rest of the install), then where files go, then knowledge base identity, then
# infrastructure (Qdrant + model cache), and finally whether to pull the
# project's skills/agents.
DEFAULT_STEPS: list[WizardStep] = [
    WizardStep(
        id="harness",
        prompt="Qual harness voce quer configurar?",
        default="claude-code",
        validator=_validate_harness,
    ),
    WizardStep(
        id="notes_root",
        prompt="Onde a instalacao do oh-my-harness sera feita?",
        default=Path.home() / "oh-my-harness",
        validator=_validate_path,
    ),
    WizardStep(
        id="kb",
        prompt="Nome da knowledge base inicial?",
        default="knowledge_base",
        validator=_validate_kb_name,
    ),
    WizardStep(
        id="qdrant_port",
        prompt="Porta local do Qdrant?",
        default=6333,
        validator=_validate_port,
    ),
    WizardStep(
        id="models_cache",
        prompt="Diretorio de cache dos modelos?",
        default=Path.home() / ".cache" / "oh-my-harness" / "models",
        validator=_validate_path,
    ),
    WizardStep(
        id="download_extras",
        prompt="Baixar skills e agents do projeto?",
        default=True,
        validator=_validate_bool,
    ),
]


# ---------------------------------------------------------------------------
# Collected choices
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InstallChoices:
    """User's configuration decisions collected by :class:`Wizard`."""

    notes_root: Path
    kb_name: str
    qdrant_port: int
    models_cache: Path
    harness: str
    download_extras: bool = True

    # Backward-compatible property so code that reads .universe still works
    # while we migrate call sites.
    @property
    def universe(self) -> str:
        return self.kb_name

    def summary(self) -> str:
        """Return a human-readable summary table."""
        from oh_my_harness.kb.agents.harness import HARNESS_REGISTRY

        h = HARNESS_REGISTRY.get(self.harness)
        harness_label = f"{self.harness}  ({h.display_path})" if h else self.harness
        extras_label = "sim" if self.download_extras else "nao"
        rules_file = h.display_path if h else "(arquivo de regras do harness)"
        lines = [
            "",
            "  Resumo da instalacao:",
            "",
            f"    Harness              {harness_label}",
            f"    Diretorio de notas   {self.notes_root}/",
            f"    Knowledge base       {self.kb_name}",
            f"    Qdrant               localhost:{self.qdrant_port}  (Docker)",
            f"    Cache de modelos     {self.models_cache}/",
            f"    Skills + agents      {extras_label}",
            "",
            "  As seguintes alteracoes serao feitas na sua maquina:",
            f"    * Container Docker qdrant/qdrant iniciado na porta {self.qdrant_port}",
            f"    * Diretorio {self.notes_root}/{self.kb_name}/ criado",
            "    * ~/.config/oh-my-harness/config.toml criado/atualizado",
            f"    * {rules_file} modificado (bloco omh inserido no inicio)",
            "",
        ]
        return "\n".join(lines)

    def confirm(self) -> bool:
        """Ask for confirmation; default is *no* (safe)."""
        return typer.confirm("Prosseguir?", default=False)


# ---------------------------------------------------------------------------
# Wizard runner
# ---------------------------------------------------------------------------


class Wizard:
    """Sequential prompt wizard.

    Args:
        steps: Ordered list of :class:`WizardStep` to run.
        non_interactive: If ``True`` all defaults are accepted silently
            (equivalent to ``--yes``).
        prefill: Optional dict mapping step ids to pre-supplied values
            (used in tests and ``--yes`` mode to override individual steps).
    """

    def __init__(
        self,
        steps: list[WizardStep] | None = None,
        non_interactive: bool = False,
        prefill: dict[str, Any] | None = None,
    ) -> None:
        self._steps = steps if steps is not None else list(DEFAULT_STEPS)
        self._non_interactive = non_interactive
        self._prefill: dict[str, Any] = prefill or {}

    def _ask(self, step: WizardStep) -> Any:
        """Ask for a single step value, returning the default in non-interactive mode."""
        if step.id in self._prefill:
            raw = self._prefill[step.id]
        elif self._non_interactive or not sys.stdin.isatty():
            raw = step.default
        else:
            default_str = _display_default(step.default)
            raw = typer.prompt(step.prompt, default=default_str)

        if step.validator is not None:
            return step.validator(raw)
        return raw

    def _print_header(self) -> None:
        typer.echo("")
        typer.secho(
            "  oh-my-harness -- Setup Wizard",
            fg=typer.colors.CYAN,
            bold=True,
        )
        typer.echo("")
        typer.echo(
            "  Bem-vindo ao oh-my-harness. Vamos configurar seu harness, "
            "a knowledge base e os extras do projeto."
        )
        typer.echo("  Pressione Enter para aceitar o valor padrao de cada opcao.")
        typer.echo("")

    def _print_step_header(self, index: int, total: int, step: WizardStep) -> None:
        typer.echo(f"  {'─' * 50}")
        typer.echo(f"  {index} / {total}  {step.prompt}")
        typer.echo("")

    def run(self) -> InstallChoices:
        """Run all steps and return the collected choices.

        In non-interactive mode the summary is printed but confirmation
        is skipped (caller is responsible for respecting ``--yes``).
        """
        self._print_header()
        total = len(self._steps)
        results: dict[str, Any] = {}

        for i, step in enumerate(self._steps, start=1):
            self._print_step_header(i, total, step)

            # Show harness selector UI for the harness step
            if step.id == "harness":
                value = self._run_harness_step(step)
            else:
                typer.echo(f"  Default: {_display_default(step.default)}")
                value = self._ask(step)

            results[step.id] = value
            typer.echo("")

        return InstallChoices(
            notes_root=results["notes_root"],
            kb_name=results["kb"],
            qdrant_port=results["qdrant_port"],
            models_cache=results["models_cache"],
            harness=results["harness"],
            download_extras=results.get("download_extras", True),
        )

    def _run_harness_step(self, step: WizardStep) -> str:
        """Show a selector for the harness step.

        Displays selectable harnesses and 'coming soon' placeholders.
        In non-interactive mode returns the default.
        """
        from oh_my_harness.kb.agents.harness import HARNESS_COMING_SOON, HARNESS_REGISTRY

        selectable = [
            name for name in HARNESS_REGISTRY if name not in HARNESS_COMING_SOON
        ]
        coming_soon = HARNESS_COMING_SOON

        options: list[tuple[str, bool]] = []
        for name in selectable:
            h = HARNESS_REGISTRY[name]
            label = f"{name:<20} {h.display_label}  ({h.display_path})"
            options.append((label, True))
        for name in coming_soon:
            label = f"{name:<20} Em breve"
            options.append((label, False))

        for idx, (label, available) in enumerate(options, start=1):
            marker = f"  {idx}." if available else "  -."
            typer.echo(f"{marker} {label}")

        typer.echo("")

        if self._non_interactive or not sys.stdin.isatty():
            # Return the first selectable harness as default
            return selectable[0] if selectable else str(step.default)

        choice_str = typer.prompt(
            "  Escolha um numero (ou Enter para o padrao claude-code)",
            default="1",
        )
        choice_str = choice_str.strip()

        # Parse selection
        try:
            choice_idx = int(choice_str) - 1
        except ValueError:
            typer.echo("  Entrada invalida, usando claude-code.")
            return selectable[0] if selectable else str(step.default)

        if choice_idx < 0 or choice_idx >= len(options):
            typer.echo("  Opcao fora do range, usando claude-code.")
            return selectable[0] if selectable else str(step.default)

        _, available = options[choice_idx]
        if not available:
            typer.echo("  Esse harness ainda nao esta disponivel, usando claude-code.")
            return selectable[0] if selectable else str(step.default)

        # Map choice_idx back to name
        if choice_idx < len(selectable):
            return selectable[choice_idx]
        return selectable[0] if selectable else str(step.default)
