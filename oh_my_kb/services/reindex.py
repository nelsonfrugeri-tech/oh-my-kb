"""Reindex service — reconcile Qdrant with markdown files on disk.

The canonical source of truth for which notes *exist* is the filesystem.
``reindex_universe`` performs a full reconciliation:

1. Discover all ``.md`` files under ``notes_root``, parse each one with
   :func:`~oh_my_kb.core.from_markdown`, and upsert the Qdrant point for
   the note (fresh embedding + current on-disk path).

2. Delete any Qdrant points whose ``path`` payload no longer corresponds to
   an existing file — these are *orphans* left behind when a note was deleted
   from disk without going through the MCP tool.

Idempotency: running twice in a row produces the same Qdrant state.

:class:`ReindexService` is a thin class wrapper around :func:`reindex_universe`
that accepts pre-constructed ``indexer`` — useful when callers already hold that
object and want to avoid re-creation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from oh_my_kb.core import from_markdown
from oh_my_kb.services.indexer import Indexer, collection_name_for

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReindexReport:
    """Summary produced by :func:`reindex_universe`."""

    scanned: int
    upserted: int
    removed: int

    def __str__(self) -> str:
        return (
            f"reindex: scanned {self.scanned} .md files; "
            f"upserted {self.upserted} points; "
            f"removed {self.removed} orphans"
        )


def reindex_universe(
    indexer: Indexer,
    universe: str,
    notes_root: Path,
) -> ReindexReport:
    """Reconcile the Qdrant collection for ``universe`` with files in ``notes_root``.

    Parameters
    ----------
    indexer:
        Fully wired :class:`Indexer` (store + embedder + notes_root).  The
        ``notes_root`` on this indexer is used as the root from which relative
        paths are resolved and stored in payloads.
    universe:
        The universe name whose collection will be reconciled.
    notes_root:
        Directory to scan for ``.md`` files.  Typically ``indexer.notes_root``,
        but passed explicitly so the function signature is testable in isolation.

    Returns
    -------
    ReindexReport
        A summary of the reconciliation.
    """
    collection = collection_name_for(universe)
    # Intentional private access — same package, avoids adding a public getter.
    store = indexer._store

    # Step 0: ensure the collection exists so scroll calls don't crash on an
    # empty universe.
    store.ensure_collection(collection)

    # -----------------------------------------------------------------------
    # Step 1: scan the filesystem and build a map of note id → absolute path.
    # Files that cannot be parsed (missing frontmatter, bad YAML, etc.) are
    # logged as warnings and skipped — a single malformed file must not abort
    # the whole reindex.
    # -----------------------------------------------------------------------
    disk_notes: dict[str, Path] = {}  # note id (str) → absolute path
    scanned = 0

    for md_path in sorted(notes_root.rglob("*.md")):
        scanned += 1
        try:
            note = from_markdown(md_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("reindex: skipping %s — parse error: %s", md_path, exc)
            continue
        disk_notes[str(note.id)] = md_path

    # -----------------------------------------------------------------------
    # Step 2: upsert every note found on disk.
    # -----------------------------------------------------------------------
    upserted = 0
    for note_id_str, abs_path in disk_notes.items():
        try:
            note = from_markdown(abs_path.read_text(encoding="utf-8"))
            indexer.upsert_from_disk(note, abs_path)
            upserted += 1
        except Exception as exc:
            logger.warning(
                "reindex: failed to upsert %s (%s) — %s", abs_path, note_id_str, exc
            )

    # -----------------------------------------------------------------------
    # Step 3: scroll all Qdrant points and remove orphans whose file is gone.
    # -----------------------------------------------------------------------
    orphan_ids: list[str] = []
    offset: str | None = None

    while True:
        response = store.client.scroll(
            collection_name=collection,
            scroll_filter=None,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        records, next_offset = response

        for record in records:
            payload = record.payload or {}
            path_str = payload.get("path")
            if not isinstance(path_str, str):
                # Corrupt point — treat as orphan.
                orphan_ids.append(str(record.id))
                continue
            abs_path = notes_root / path_str
            if not abs_path.exists():
                orphan_ids.append(str(record.id))

        if next_offset is None:
            break
        offset = str(next_offset)

    removed = 0
    if orphan_ids:
        store.client.delete(
            collection_name=collection,
            points_selector=orphan_ids,  # type: ignore[arg-type]
        )
        removed = len(orphan_ids)

    report = ReindexReport(scanned=scanned, upserted=upserted, removed=removed)
    logger.info("%s", report)
    return report


class ReindexService:
    """Class wrapper around :func:`reindex_universe` for dependency-injected callers.

    Holds a pre-constructed :class:`Indexer` and delegates every call to the
    functional implementation so logic lives in exactly one place.
    """

    def __init__(self, indexer: Indexer) -> None:
        self._indexer = indexer

    def reindex(self, universe: str) -> ReindexReport:
        """Reconcile the Qdrant collection for ``universe`` with files on disk.

        Delegates to :func:`reindex_universe` using the injected indexer's
        ``notes_root`` as the scan directory.
        """
        return reindex_universe(
            indexer=self._indexer,
            universe=universe,
            notes_root=self._indexer.notes_root,
        )
