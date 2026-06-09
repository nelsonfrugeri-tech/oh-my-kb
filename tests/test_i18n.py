import pytest

from oh_my_harness.kb.i18n import BASE_LOCALE, DEFAULT_LOCALE, resolve_locale_path


def test_constants():
    assert DEFAULT_LOCALE == "pt-BR"
    assert BASE_LOCALE == "pt-BR"


def test_resolve_exact_locale(tmp_path):
    (tmp_path / "pt-BR").mkdir()
    (tmp_path / "pt-BR" / "file.md").write_text("pt-BR content")
    path = resolve_locale_path(tmp_path, "file.md", "pt-BR")
    assert path.read_text() == "pt-BR content"


def test_resolve_fallback_to_base(tmp_path):
    """When requested locale missing, falls back to BASE_LOCALE (pt-BR)."""
    (tmp_path / "pt-BR").mkdir()
    (tmp_path / "pt-BR" / "file.md").write_text("fallback content")
    # en-US dir does not exist
    path = resolve_locale_path(tmp_path, "file.md", "en-US")
    assert path.read_text() == "fallback content"


def test_resolve_raises_when_neither_exists(tmp_path):
    """Raises FileNotFoundError when locale and fallback both missing."""
    (tmp_path / "pt-BR").mkdir()
    # file not created — missing
    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_locale_path(tmp_path, "missing.md", "en-US")
    assert "missing.md" in str(exc_info.value)


def test_resolve_default_locale(tmp_path):
    """resolve_locale_path uses DEFAULT_LOCALE when locale not supplied."""
    (tmp_path / "pt-BR").mkdir()
    (tmp_path / "pt-BR" / "rules.md").write_text("default locale content")
    path = resolve_locale_path(tmp_path, "rules.md")
    assert path.read_text() == "default locale content"


def test_changing_locale_returns_different_file(tmp_path):
    """Passing a different locale returns a different file (key for future language-option)."""
    (tmp_path / "pt-BR").mkdir()
    (tmp_path / "en-US").mkdir()
    (tmp_path / "pt-BR" / "f.md").write_text("pt conteúdo")
    (tmp_path / "en-US" / "f.md").write_text("en content")
    pt = resolve_locale_path(tmp_path, "f.md", "pt-BR")
    en = resolve_locale_path(tmp_path, "f.md", "en-US")
    assert pt.read_text() == "pt conteúdo"
    assert en.read_text() == "en content"
