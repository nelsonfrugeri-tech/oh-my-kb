from oh_my_harness.kb.agents.template import load_template, render_dynamic_block, render_rules


def test_load_template_returns_pt_br():
    content = load_template()
    assert "{kb_name}" in content  # placeholder present
    assert "pt-BR" in content  # content_version marker


def test_render_rules_substitutes_kb_name():
    result = render_rules("my-kb")
    assert "{kb_name}" not in result
    assert "my-kb" in result


def test_load_template_fallback(tmp_path, monkeypatch):
    """Unknown locale falls back to pt-BR without raising."""
    import oh_my_harness.kb.agents.template as template_mod
    monkeypatch.setattr(template_mod, "_AGENTS_DIR", tmp_path)
    (tmp_path / "pt-BR").mkdir()
    (tmp_path / "pt-BR" / "rules_template.md").write_text("rules for {universe}")
    content = load_template(locale="xx-XX")
    assert content == "rules for {universe}"


def test_render_dynamic_block_contains_agents_section():
    result = render_dynamic_block("test-universe")
    assert "Agentes pessoais (o-agents-mcp)" in result
    assert "develop_leap_update" in result


def test_render_dynamic_block_contains_trigger_phrases():
    result = render_dynamic_block("test-universe")
    assert "atualize minhas preferências" in result
