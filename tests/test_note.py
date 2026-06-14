from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from oh_my_harness.kb.core import Note, NoteType


def _minimal_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Desenho das tools",
        "type": NoteType.DECISION,
        "project": "oh-my-harness",
        "kb_name": "engineering",
        "summary": "Decisão arquitetural sobre as tools do MCP.",
    }
    payload.update(overrides)
    return payload


def _make_note(**overrides: object) -> Note:
    return Note(**_minimal_payload(**overrides))  # type: ignore[arg-type]


def test_minimal_construction_populates_defaults() -> None:
    note = _make_note()

    assert isinstance(note.id, UUID)
    assert note.created_at.tzinfo is not None
    assert note.entities == []
    assert note.links_out == []
    assert note.supersedes is None
    assert note.archived is False
    assert note.body == ""


def test_each_instance_gets_a_unique_id() -> None:
    a, b = _make_note(), _make_note()
    assert a.id != b.id


def test_id_is_immutable() -> None:
    note = _make_note()
    with pytest.raises(ValidationError):
        note.id = uuid4()  # type: ignore[misc]


def test_invalid_type_value_raises() -> None:
    with pytest.raises(ValidationError):
        Note.model_validate(_minimal_payload(type="not-a-type"))


@pytest.mark.parametrize("field", ["title", "project", "kb_name", "summary"])
@pytest.mark.parametrize("bad_value", ["", "   ", "\t\n"])
def test_required_string_fields_reject_empty_or_whitespace(field: str, bad_value: str) -> None:
    with pytest.raises(ValidationError):
        Note.model_validate(_minimal_payload(**{field: bad_value}))


def test_created_at_must_be_tz_aware() -> None:
    naive = datetime(2026, 5, 31, 12, 0)
    with pytest.raises(ValidationError):
        Note.model_validate(_minimal_payload(created_at=naive))


def test_default_created_at_is_tz_aware() -> None:
    note = _make_note()
    assert note.created_at.tzinfo is not None


def test_slug_auto_derived_from_title_and_created_at() -> None:
    note = _make_note(created_at=datetime(2026, 5, 31, tzinfo=UTC))
    assert note.slug == "2026-05-31-desenho-das-tools"


def test_explicit_slug_is_preserved() -> None:
    note = _make_note(slug="my-custom-slug")
    assert note.slug == "my-custom-slug"


def test_accepts_optional_fields() -> None:
    target = uuid4()
    superseded = uuid4()
    note = _make_note(
        entities=["alice", "bob"],
        links_out=[target],
        supersedes=superseded,
        archived=True,
        body="# Detailed notes\n\nLorem ipsum.",
    )
    assert note.entities == ["alice", "bob"]
    assert note.links_out == [target]
    assert note.supersedes == superseded
    assert note.archived is True
    assert "Lorem ipsum" in note.body


def test_type_accepts_string_alias() -> None:
    note = Note.model_validate(_minimal_payload(type="event"))
    assert note.type is NoteType.EVENT


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Note.model_validate(_minimal_payload(unknown_field="oops"))
