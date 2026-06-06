"""Template loader — reads rules_template.md via importlib.resources."""

from __future__ import annotations

from importlib.resources import files


def load_template() -> str:
    """Return the raw text of ``rules_template.md`` bundled with this package."""
    return files("oh_my_kb.agents").joinpath("rules_template.md").read_text(encoding="utf-8")


def render_rules(universe: str) -> str:
    """Return the rules block with ``{universe}`` substituted."""
    return load_template().replace("{universe}", universe)
