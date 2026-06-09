from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from oh_my_harness.kb.mcp.tools.kb_write import handle_kb_write
from oh_my_harness.kb.services import Indexer

# ``indexer`` fixture is provided by tests/conftest.py.

_LONG_VALID_SUMMARY = (
    "Resumo denso suficiente para passar pela faixa de comprimento mínima "
    "definida pela validação leve no caminho de kb_write. O conteúdo aqui "
    "é técnico para não cair na heurística de label/título; descreve o "
    "comportamento esperado do handler de validação para os casos onde os "
    "OUTROS campos é que falham (type fora do enum, title vazio, etc.)."
)


async def test_kb_write_persists_minimal_note(indexer: Indexer, tmp_path: Path) -> None:
    args = {
        "title": "Test decision",
        "type": "decision",
        "project": "oh-my-harness",
        "summary": (
            "Decisão de validar o caminho mínimo de kb_write: aceita os "
            "campos obrigatórios (title, type, project, summary), persiste o "
            ".md no filesystem sob notes_root e indexa o ponto no Qdrant "
            "com vetores nomeados dense e sparse. Os campos opcionais "
            "(body, entities, links_out, supersedes, archived) seguem os "
            "defaults do modelo Note quando ausentes."
        ),
    }
    result = await handle_kb_write(indexer, "engineering", args)

    assert len(result) == 1
    text = result[0].text
    assert "kb_write: wrote note" in text
    assert "id:" in text
    assert "slug:" in text
    assert "path:" in text
    assert "universe:engineering" in text

    md_files = list(tmp_path.rglob("*.md"))
    assert len(md_files) == 1


async def test_kb_write_persists_full_note(indexer: Indexer) -> None:
    superseded = uuid4()
    link_target = uuid4()
    args = {
        "title": "Full note",
        "type": "reference",
        "project": "oh-my-harness",
        "summary": (
            "Cobertura de todos os campos opcionais de kb_write num único "
            "caso: body markdown, entities como lista de strings, links_out "
            "como UUIDs, supersedes apontando para um id existente e "
            "archived explícito. Serve para garantir que cada slot do "
            "schema é repassado corretamente para o Note model e para o "
            "Indexer antes do upsert no Qdrant."
        ),
        "body": "# Body\n\nLong-form markdown.",
        "entities": ["nelson", "qdrant"],
        "links_out": [str(link_target)],
        "supersedes": str(superseded),
        "archived": False,
    }
    result = await handle_kb_write(indexer, "engineering", args)
    assert "kb_write: wrote note" in result[0].text


async def test_kb_write_invalid_type_returns_error_text(indexer: Indexer) -> None:
    args = {
        "title": "Bad type",
        "type": "not-a-real-type",
        "project": "oh-my-harness",
        "summary": _LONG_VALID_SUMMARY,
    }
    result = await handle_kb_write(indexer, "engineering", args)
    assert len(result) == 1
    assert "invalid input" in result[0].text


async def test_kb_write_empty_title_returns_error_text(indexer: Indexer) -> None:
    args = {
        "title": "   ",
        "type": "decision",
        "project": "oh-my-harness",
        "summary": _LONG_VALID_SUMMARY,
    }
    result = await handle_kb_write(indexer, "engineering", args)
    assert "invalid input" in result[0].text


async def test_kb_write_universe_is_server_bound_not_input(indexer: Indexer) -> None:
    args = {
        "title": "Server universe wins",
        "type": "decision",
        "project": "oh-my-harness",
        "summary": _LONG_VALID_SUMMARY,
        # Note: inputSchema additionalProperties=False would block this in MCP,
        # but the handler also doesn't *consume* a universe from args.
    }
    result = await handle_kb_write(indexer, "research", args)
    assert "universe:research" in result[0].text


# --- new in #12: light summary validation -------------------------------


async def test_kb_write_summary_too_short_returns_error(indexer: Indexer) -> None:
    args = {
        "title": "Short summary",
        "type": "decision",
        "project": "oh-my-harness",
        "summary": "Decisão curta demais.",
    }
    result = await handle_kb_write(indexer, "engineering", args)
    text = result[0].text
    assert "invalid input" in text
    assert "too short" in text


async def test_kb_write_summary_too_long_returns_error(indexer: Indexer) -> None:
    args = {
        "title": "Long summary",
        "type": "decision",
        "project": "oh-my-harness",
        "summary": "a" * 801,
    }
    result = await handle_kb_write(indexer, "engineering", args)
    text = result[0].text
    assert "invalid input" in text
    assert "too long" in text


async def test_kb_write_summary_equal_to_title_returns_error(
    indexer: Indexer,
) -> None:
    repeated = (
        "Decisão sobre a arquitetura do oh-my-harness com bge-m3 e Qdrant para "
        "implementar busca híbrida (dense + sparse) com fusão RRF nativa "
        "e indexação per-universe; a escolha desvia do uso de FastEmbed "
        "porque a versão atual não suporta o modelo bge-m3."
    )
    args = {
        "title": repeated,
        "type": "decision",
        "project": "oh-my-harness",
        "summary": repeated,
    }
    result = await handle_kb_write(indexer, "engineering", args)
    text = result[0].text
    assert "invalid input" in text
    assert "identical to the title" in text
