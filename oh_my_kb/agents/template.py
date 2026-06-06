"""Agent bootstrap rules template loader (locale-aware)."""

from __future__ import annotations

from pathlib import Path

from oh_my_kb.i18n import DEFAULT_LOCALE, resolve_locale_path

_AGENTS_DIR: Path = Path(__file__).parent
_RULES_FILENAME: str = "rules_template.md"


def load_template(locale: str = DEFAULT_LOCALE) -> str:
    """Return the raw rules_template.md for the requested locale, with fallback."""
    path = resolve_locale_path(_AGENTS_DIR, _RULES_FILENAME, locale=locale)
    return path.read_text(encoding="utf-8")


def render_rules(universe: str, locale: str = DEFAULT_LOCALE) -> str:
    """Return the bootstrap rules with ``{universe}`` substituted."""
    return load_template(locale=locale).replace("{universe}", universe)
