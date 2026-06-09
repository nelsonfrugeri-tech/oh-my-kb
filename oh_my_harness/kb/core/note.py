"""Domain model for a knowledge-base note.

The note is the atomic unit of the system. Its canonical identity is the
immutable UUID `id`; the `slug` is a human-readable file-name component and
links between notes always reference the UUID, so a slug can be regenerated
or a file renamed without breaking relationships.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from oh_my_harness.kb.core.slug import generate_slug


class NoteType(StrEnum):
    DECISION = "decision"
    EVENT = "event"
    PROCEDURE = "procedure"
    REFERENCE = "reference"
    CONVERSATION = "conversation"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Note(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4, frozen=True)
    slug: str = ""
    title: str
    type: NoteType
    project: str
    universe: str
    created_at: datetime = Field(default_factory=_utc_now)
    entities: list[str] = Field(default_factory=list)
    links_out: list[UUID] = Field(default_factory=list)
    supersedes: UUID | None = None
    archived: bool = False
    summary: str
    body: str = ""

    @field_validator("title", "project", "universe", "summary")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty or whitespace")
        return value

    @field_validator("created_at")
    @classmethod
    def _require_tzaware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _ensure_slug(self) -> Note:
        if not self.slug:
            object.__setattr__(self, "slug", generate_slug(self.title, self.created_at))
        return self
