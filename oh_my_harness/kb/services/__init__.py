from oh_my_harness.kb.services.indexer import (
    Indexer,
    NoteNotFoundError,
    collection_name_for,
)
from oh_my_harness.kb.services.navigation import (
    ExpandResult,
    NavigationService,
    ResolvedLink,
    TreeNode,
)
from oh_my_harness.kb.services.paths import (
    NOTES_ROOT_ENV,
    get_notes_root,
)
from oh_my_harness.kb.services.recent import RecentService
from oh_my_harness.kb.services.reindex import (
    ReindexReport,
    ReindexService,
    reindex_kb,
    reindex_universe,  # backward-compatible alias
)
from oh_my_harness.kb.services.search import SearchResult, SearchService

__all__ = [
    "NOTES_ROOT_ENV",
    "ExpandResult",
    "Indexer",
    "NavigationService",
    "NoteNotFoundError",
    "RecentService",
    "ReindexReport",
    "ReindexService",
    "ResolvedLink",
    "SearchResult",
    "SearchService",
    "TreeNode",
    "collection_name_for",
    "get_notes_root",
    "reindex_kb",
    "reindex_universe",  # backward-compatible alias
]
