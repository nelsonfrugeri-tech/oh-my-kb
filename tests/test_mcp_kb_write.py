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


async def test_kb_write_persists_minimal_note(indexer: Indexer, tmp_path: Path) -> None:
    args = {
        "title": "Test decision",
        "type": "decision",
        "project": "oh-my-kb",
        "summary": "Decisão de validar o caminho mínimo de kb_write.",
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
        "summary": "Cobertura de todos os campos opcionais.",
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
        "summary": "should fail validation",
    }
    result = await handle_kb_write(indexer, "engineering", args)
    assert len(result) == 1
    assert "invalid input" in result[0].text


async def test_kb_write_empty_title_returns_error_text(indexer: Indexer) -> None:
    args = {
        "title": "   ",
        "type": "decision",
        "project": "oh-my-kb",
        "summary": "non-empty title required",
    }
    result = await handle_kb_write(indexer, "engineering", args)
    assert "invalid input" in result[0].text


async def test_kb_write_universe_is_server_bound_not_input(indexer: Indexer) -> None:
    args = {
        "title": "Server universe wins",
        "type": "decision",
        "project": "oh-my-kb",
        "summary": "Even if input had a universe field, server's would win.",
        # Note: inputSchema additionalProperties=False would block this in MCP,
        # but the handler also doesn't *consume* a universe from args.
    }
    result = await handle_kb_write(indexer, "research", args)
    assert "universe:research" in result[0].text
