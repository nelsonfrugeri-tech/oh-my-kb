from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from oh_my_kb.embedding import Embedder, EmbeddingResult, SparseVector
from oh_my_kb.mcp.tools.kb_write import handle_kb_write
from oh_my_kb.services import Indexer
from oh_my_kb.storage import DENSE_DIM, IN_MEMORY, QdrantStore


class _StubEmbedder(Embedder):
    @property
    def dense_dim(self) -> int:
        return DENSE_DIM

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        results: list[EmbeddingResult] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            dense = [digest[i % 32] / 255.0 for i in range(DENSE_DIM)]
            sparse = SparseVector(
                indices=[int.from_bytes(digest[0:2], "little")],
                values=[1.0],
            )
            results.append(EmbeddingResult(dense=dense, sparse=sparse))
        return results


@pytest.fixture
def indexer(tmp_path: Path) -> Indexer:
    return Indexer(
        store=QdrantStore(IN_MEMORY),
        embedder=_StubEmbedder(),
        notes_root=tmp_path,
    )


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
        "project": "oh-my-kb",
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
        "project": "oh-my-kb",
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
        "project": "oh-my-kb",
        "summary": _LONG_VALID_SUMMARY,
    }
    result = await handle_kb_write(indexer, "engineering", args)
    assert len(result) == 1
    assert "invalid input" in result[0].text


async def test_kb_write_empty_title_returns_error_text(indexer: Indexer) -> None:
    args = {
        "title": "   ",
        "type": "decision",
        "project": "oh-my-kb",
        "summary": _LONG_VALID_SUMMARY,
    }
    result = await handle_kb_write(indexer, "engineering", args)
    assert "invalid input" in result[0].text


async def test_kb_write_universe_is_server_bound_not_input(indexer: Indexer) -> None:
    args = {
        "title": "Server universe wins",
        "type": "decision",
        "project": "oh-my-kb",
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
        "project": "oh-my-kb",
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
        "project": "oh-my-kb",
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
        "Decisão sobre a arquitetura do oh-my-kb com bge-m3 e Qdrant para "
        "implementar busca híbrida (dense + sparse) com fusão RRF nativa "
        "e indexação per-universe; a escolha desvia do uso de FastEmbed "
        "porque a versão atual não suporta o modelo bge-m3."
    )
    args = {
        "title": repeated,
        "type": "decision",
        "project": "oh-my-kb",
        "summary": repeated,
    }
    result = await handle_kb_write(indexer, "engineering", args)
    text = result[0].text
    assert "invalid input" in text
    assert "identical to the title" in text
