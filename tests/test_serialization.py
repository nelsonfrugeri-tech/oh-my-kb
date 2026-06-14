from datetime import UTC, datetime
from uuid import UUID

import pytest

from oh_my_harness.kb.core import Note, NoteType, from_markdown, to_markdown


def _fully_populated_note() -> Note:
    return Note(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        slug="2026-05-31-arquitetura-do-kb",
        title="Arquitetura do KB",
        type=NoteType.DECISION,
        project="oh-my-harness",
        kb_name="engineering",
        created_at=datetime(2026, 5, 31, 14, 30, tzinfo=UTC),
        entities=["nelson", "qdrant"],
        links_out=[
            UUID("22222222-2222-4222-8222-222222222222"),
            UUID("33333333-3333-4333-8333-333333333333"),
        ],
        supersedes=UUID("44444444-4444-4444-8444-444444444444"),
        archived=False,
        summary="Define como os módulos core/mcp/cli se relacionam.",
        body="# Arquitetura\n\nNotas detalhadas sobre o desenho.",
    )


def _minimal_note() -> Note:
    return Note(
        title="Minimal note",
        type=NoteType.REFERENCE,
        project="oh-my-harness",
        kb_name="engineering",
        summary="Apenas o necessário.",
    )


def test_to_markdown_produces_frontmatter_then_body() -> None:
    md = to_markdown(_fully_populated_note())
    assert md.startswith("---")
    assert "title: " in md
    assert "# Arquitetura" in md  # body content present
    # Front-matter must come before the body.
    assert md.index("title:") < md.index("# Arquitetura")


def test_round_trip_preserves_all_fields_for_a_fully_populated_note() -> None:
    original = _fully_populated_note()
    restored = from_markdown(to_markdown(original))
    assert restored == original


def test_round_trip_preserves_minimal_note() -> None:
    original = _minimal_note()
    restored = from_markdown(to_markdown(original))
    assert restored == original


def test_round_trip_preserves_empty_body() -> None:
    original = _minimal_note()
    assert original.body == ""
    restored = from_markdown(to_markdown(original))
    assert restored.body == ""


def test_from_markdown_missing_required_field_raises() -> None:
    md = """---
id: 11111111-1111-4111-8111-111111111111
slug: 2026-05-31-no-title
type: decision
project: oh-my-harness
universe: engineering
created_at: '2026-05-31T14:30:00+00:00'
summary: faltando o title
---

corpo
"""
    with pytest.raises(ValueError):
        from_markdown(md)


def test_from_markdown_malformed_yaml_raises() -> None:
    md = """---
title: "unterminated string
type: decision
---

corpo
"""
    with pytest.raises(ValueError):
        from_markdown(md)


def test_from_markdown_invalid_type_value_raises() -> None:
    md = """---
id: 11111111-1111-4111-8111-111111111111
slug: 2026-05-31-bad-type
title: Bad type
type: not-a-real-type
project: oh-my-harness
universe: engineering
created_at: '2026-05-31T14:30:00+00:00'
summary: tipo inválido
---

corpo
"""
    with pytest.raises(ValueError):
        from_markdown(md)
