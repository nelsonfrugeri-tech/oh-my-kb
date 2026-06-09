"""Round-trip serialization between :class:`Note` and ``.md`` with YAML front-matter.

Every field except :attr:`Note.body` lives in the front-matter block; the body
follows as plain markdown. ``from_markdown(to_markdown(note))`` reconstructs a
:class:`Note` equivalent to the original.
"""

from __future__ import annotations

from typing import Any

import frontmatter

from oh_my_harness.kb.core.note import Note


def to_markdown(note: Note) -> str:
    """Serialize ``note`` to a markdown string with YAML front-matter."""
    metadata: dict[str, Any] = note.model_dump(mode="json", exclude={"body"})
    post = frontmatter.Post(note.body, **metadata)
    return frontmatter.dumps(post)


def from_markdown(content: str) -> Note:
    """Parse and validate a markdown string into a :class:`Note`.

    Raises :class:`ValueError` if the front-matter is malformed. Validation
    errors (missing required fields, invalid enum values, etc.) propagate as
    :class:`pydantic.ValidationError`, which itself is a :class:`ValueError`.
    """
    try:
        post = frontmatter.loads(content)
    except Exception as exc:
        raise ValueError(f"malformed front-matter: {exc}") from exc
    data: dict[str, Any] = dict(post.metadata)
    data["body"] = post.content
    return Note.model_validate(data)
