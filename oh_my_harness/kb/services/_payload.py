"""Shared payload helpers for search and recent services.

``SearchResult`` and ``require_payload_fields`` used to live in
``services.search``.  Both are now in this internal module so that
``services.recent`` can import them without coupling to a "private" symbol
of a sibling service.

The old name ``_require_payload_fields`` (with underscore) is re-exported
from ``services.search`` for backwards compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Payload carried back from a hybrid-search or temporal-recall hit.

    ``score`` is an RRF rank-fusion score for with-topic results, or ``0.0``
    for no-topic results ordered by ``created_at``.  Do not interpret ``0.0``
    as a relevance score — the MCP handler labels it "n/a".

    ``path`` is **relative to the knowledge base's** ``notes_root`` (matches the
    Indexer payload, kept relative for portability across machines). The
    caller resolves it to an absolute path via the notes_root it already
    knows for the knowledge base being searched.

    Fields intentionally omitted for now: the ``universe`` payload key, ``entities``,
    ``supersedes``. They can be added when a downstream consumer needs them.
    See issue #9 for the full payload spec discussion.
    """

    id: str
    title: str
    summary: str
    type: str
    project: str
    archived: bool
    created_at: datetime
    path: str
    score: float


def require_payload_fields(
    point_id: object, payload: dict[str, object], fields: tuple[str, ...]
) -> None:
    """Raise if any required payload field is absent.

    A missing ``id`` or ``path`` means the index is corrupt (written by an
    older version of the Indexer or an external tool that skipped required
    fields). Silently substituting a fallback would hide the corruption and
    produce hard-to-debug downstream errors.
    """
    missing = [f for f in fields if f not in payload]
    if missing:
        raise RuntimeError(
            f"Index point {point_id!r} is missing required payload fields: {missing}. "
            "Re-index the affected notes to repair the index."
        )
