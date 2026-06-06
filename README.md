# oh-my-kb

Their knowledge is their universe. A programmatic, agnostic knowledge base exposed via MCP, with markdown notes indexed in Qdrant for hybrid search.

## Architecture

Domain logic lives in `oh_my_kb/core/` with no MCP, CLI, or network dependencies. The MCP server (`oh_my_kb/mcp/`) and CLI (`oh_my_kb/cli/`) are thin adapters over `core`, so a future `o-kb-sdk` can reuse the same logic.

```
oh_my_kb/
  core/       # pure domain logic — no MCP / CLI / network
  storage/    # infrastructure adapters (Qdrant)
  embedding/  # embedding interface + bge-m3 implementation
  services/   # application services (Indexer, SearchService)
  cli/        # o-kb-client (omk) — install + multiverse management
  mcp/        # MCP server adapter (knowledge interaction only)
tests/
```

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- `make`
- Docker + Docker Compose (for the local Qdrant)

## Usage

All workflows are wrapped by `make`. Run `make` (or `make help`) to list every target.

```bash
make install    # create .venv and install all dependencies (uv sync)
make test       # run the test suite (uv run pytest)
make lint       # lint with ruff
make format     # format with ruff
make typecheck  # type-check with mypy
make check      # lint + typecheck + test (the CI gate)
make clean      # remove .venv and tool caches
```

`make venv` and `make sync` are aliases for `make install`.

## Local infrastructure (Qdrant)

The hybrid search index lives in Qdrant. A `docker-compose.yml` at the repo
root brings up a local instance with a persistent volume at `./.data/qdrant`
(git-ignored).

```bash
docker compose up -d   # start Qdrant (HTTP on 6333, gRPC on 6334)
docker compose down    # stop it
```

The storage adapter reads the URL from the `KB_QDRANT_URL` env var, falling
back to `http://localhost:6333`. Tests use the qdrant-client `:memory:`
backend, so Docker is not required to run the suite.

## Embedding

Hybrid retrieval uses [bge-m3](https://huggingface.co/BAAI/bge-m3) via
`FlagEmbedding`, producing a 1024-dim dense vector plus a lexical sparse
vector from a single model. The implementation lives in
`oh_my_kb/embedding/bge_m3_embedder.py` behind the abstract
`Embedder` interface (`oh_my_kb/embedding/base.py`).

The first run downloads ~2 GB of model weights from HuggingFace into
`~/.cache/huggingface`. Subsequent runs reuse the cache. Tests that load the
real model are tagged with `@pytest.mark.slow`:

```bash
make test                      # all tests, including the slow real-model run
uv run pytest -m "not slow"    # fast loop — skip the model load
```

## Notes on disk and indexing

The `Indexer` application service writes notes as `.md` files and upserts
their index entries into Qdrant.

- **Filesystem layout:** `<KB_NOTES_ROOT>/<slug(universe)>/<slug(project)>/<note.slug>.md`. `KB_NOTES_ROOT` defaults to `~/oh-my-kb`.
- **Collection naming:** one Qdrant collection per universe, named `kb_<slug(universe)>`. Search never crosses universes.
- **Indexed payload:** the note's identity + `summary` + the absolute path to the file. The full body and `links_out` are **not** stored in Qdrant — the body lives on disk and is read back via the payload's `path` when needed.

## Hybrid search

`SearchService` (`oh_my_kb/services/search.py`) turns a natural-language
query into dense + sparse vectors, asks Qdrant's Query API to prefetch the
top hits for each vector, and fuses the two ranked lists with **Reciprocal
Rank Fusion** (`Fusion.RRF`) server-side. Filters (`project`,
`archived`) are pushed down as payload conditions, so they run before
fusion rather than after.

```python
from oh_my_kb.services import SearchService

results = SearchService(store, embedder).search(
    "como armazenamos vetores?",
    universe="engineering",
    project="oh-my-kb",          # optional
    top_k=5,
    include_archived=False,      # archived notes are skipped by default
)
```

A missing universe collection is *not* an error — the service returns an
empty list. Each `SearchResult` carries `id`, `title`, `summary`, `type`,
`project`, `created_at`, `path`, and the fused `score`.

## Navigation

`NavigationService` (`oh_my_kb/services/navigation.py`) is the second way
into the knowledge base: when search-by-similarity isn't the right
abstraction (small universe, relationship-heavy structure), the harness
can ask for a *map* of the universe and then expand specific nodes.

- `get_tree(universe, project=None, include_archived=False)` — returns a
  `dict[project, list[TreeNode]]` built **entirely from Qdrant payloads**.
  No `.md` files are read. This keeps the tree cheap regardless of universe
  size and is exactly why `summary` lives in the payload.
- `expand(note_id, universe)` — reconstructs the full `Note` from disk
  (one file read) **plus** payload-only `ResolvedLink` metadata for every
  UUID in its `links_out`. Broken or archived link targets are silently
  dropped, so the harness shouldn't try to follow them.

## CLI — `omk`

The `omk` (o-kb-client) command is the user-facing entry point for **infra
and lifecycle**. Knowledge interaction (search / write) stays in MCP — the
CLI only provisions and manages the environment.

```bash
omk help                    # list every command
omk install                 # start Qdrant, ensure bge-m3, create default universe
omk universe create <name>  # add a universe (dir + collection + config entry)
omk universe list           # list configured universes ('*' marks the active one)
omk universe use <name>     # set the active universe
```

`omk install` is idempotent — re-running it just confirms the current state
(Qdrant healthy, model cached, universe + collection in place). The config
file lives at `~/.config/oh-my-kb/config.toml` (XDG-style hidden), while
note data lives in the **visible** `~/oh-my-kb/<universe>/` so notes are
easy to open, edit and version-control.

The data root can be overridden with the `KB_NOTES_ROOT` env var; the
config directory with `OMK_CONFIG_DIR` (useful for tests).

## MCP server — `o-kb-mcp`

Knowledge interaction lives in the MCP server. `o-kb-mcp` is a stdio
server that exposes four tools the harness calls into:

- **`kb_write`** — register a note (decision / event / procedure /
  reference / conversation). Validates the input via the `Note` pydantic
  model and persists the `.md` + Qdrant point via the `Indexer`. The
  active universe is **server-bound** (`KB_UNIVERSE`) so the harness can't
  write into the wrong universe by accident.
- **`kb_search`** — hybrid retrieval (`SearchService`) over the active
  universe with optional `project` and `include_archived` filters. Use
  when the question is about content or theme ("what do we know about X?").
- **`kb_recent`** — temporal recall (`RecentService`) ordered by
  `created_at` descending. Use for questions about *time* — "what changed
  recently", "latest decisions on project X", "what happened in the last 7
  days". See [Temporal recall — kb_recent](#temporal-recall--kb_recent)
  below.
- **`kb_tree`** — map the universe as a project-grouped directory of note
  summaries (id, title, type, summary per note). Use when the question is
  about what *exists* or what *relates* ("what notes are in project X?"),
  or when you need ids to pass into `kb_expand`. No semantic scoring — it
  is a structural view, not a similarity search.
- **`kb_expand`** — read a note in full (title, metadata, complete body)
  and resolve its outbound links as a list (id, title, type, summary). Use
  to follow the knowledge graph hop by hop: call `kb_expand` again on any
  link id returned here. The id comes from a prior `kb_search` hit,
  `kb_tree` row, or `kb_expand` link.

**Navigate vs. search vs. recent:** prefer `kb_tree` + `kb_expand` when
exploring structure or relationships; prefer `kb_search` when looking for
notes by semantic content; prefer `kb_recent` when the question is about
time.

The server builds its dependencies (`QdrantStore`, `BGEM3Embedder`,
`Indexer`, `SearchService`, `RecentService`, `NavigationService`) **once**
at boot and reuses them for every request — bge-m3 doesn't reload per call.

Run it directly via the installed script:

```bash
o-kb-mcp                       # stdio transport, ready to be wired into a harness
```

Environment:

- `KB_QDRANT_URL` — Qdrant URL (default `http://localhost:6333`).
- `KB_UNIVERSE` — active universe (default `default`). See [ADR-002](docs/adr/ADR-002-server-bound-universe.md) for the rationale and alternatives considered.
- `KB_NOTES_ROOT` — notes-root override for the active universe (default
  `~/oh-my-kb/<slug(universe)>`).

### Temporal recall — kb_recent

`kb_recent` answers time-based questions. Use it when the user asks about
*recency* rather than *content similarity*:

| Use case | Right tool |
|----------|------------|
| "What do we know about Qdrant?" | `kb_search` |
| "What changed in the last 7 days?" | `kb_recent` |
| "Latest decisions on project alpha" | `kb_recent` |
| "Show the knowledge map" | `kb_tree` |
| "Open a note + see what it links to" | `kb_expand` |

```python
# Recent notes — newest first (no topic)
results = recent_service.recent("engineering", limit=10)

# Within a time window
from oh_my_kb.services import parse_since
from datetime import UTC, datetime
since = parse_since("7d", now=datetime.now(tz=UTC))
results = recent_service.recent("engineering", since=since, project="oh-my-kb")

# Combine with topic: rank semantically within the window
results = recent_service.recent("engineering", topic="qdrant architecture", since=since)
```

**Accepted `since` formats:**

| Format | Example | Meaning |
|--------|---------|---------|
| Relative days | `"7d"`, `"30d"` | Last N days |
| Relative weeks | `"2w"` | Last N weeks |
| Relative hours | `"24h"` | Last N hours |
| Relative minutes | `"90m"` | Last N minutes |
| ISO date | `"2026-06-01"` | From midnight UTC on that date |
| ISO datetime (tz-aware) | `"2026-06-01T00:00:00+00:00"` | Exact UTC timestamp |

Relative unit letters are **case-insensitive** (`"7D"` and `"7d"` are equivalent).
Naive ISO datetimes (without timezone) are rejected — they are ambiguous.

When `topic` is provided the service uses RRF fusion (same path as
`kb_search`) to rank by semantic relevance within the time window.  When
`topic` is absent, results are ordered purely by `created_at` descending
and `score` is `0.0` (the MCP formatter labels it "n/a").

> **Migration note for universes created before this version:**
> Payload indexes on `created_at` (DATETIME) and `project` (KEYWORD) were added to support
> `kb_recent`. They are applied automatically by `QdrantStore.ensure_collection` on next boot
> — no manual action required. If you see `order_by` errors, restart the server to trigger
> re-application of indexes.

### Scribe skill (resources)

The server also exposes the **scribe playbook** as MCP resources so the
harness can read the same writing guidance the human team agreed on:

- `skill://scribe/SKILL.md` — judgement rules for `kb_write`: when to
  create vs. supersede, how to pick a `type`, how to write a summary
  that recalls well, how to extract entities, how to discover related
  notes for `links_out`.
- `skill://scribe/template.md` — the required structure of the note
  `body` (sections per `type`).

Until `o-kb-agents` (#18) automates the bootstrap, the harness should
**read these resources before every `kb_write`** to keep the summary
prose-shaped (the floor and ceiling — 200–800 chars, ≠ title — are
enforced server-side by `kb_write`, so violations come back as clear
tool errors). Editing the markdown reflects on the next read; no rebuild
needed.
