# oh-my-kb

> A programmatic, harness-agnostic knowledge base exposed via MCP. Notes live as plain markdown on disk and are indexed in Qdrant for hybrid search (dense + sparse via bge-m3), graph navigation (`links_out`), and temporal recall (`created_at`).

---

## What is oh-my-kb?

oh-my-kb is a personal knowledge base that any MCP-compatible AI harness (Claude Code, Claude Desktop, or anything else) can read and write through five tools. It is "agnostic" in two senses:

- It is not tied to any specific harness — the MCP server works with any client.
- It imposes no domain model — any kind of knowledge fits inside five note types: `decision`, `event`, `procedure`, `reference`, `conversation`.

Notes are stored as plain markdown files on disk so you can read, version-control, or edit them with any tool. Qdrant indexes the notes for hybrid semantic search, combining a 1024-dim dense vector and a lexical sparse vector from a single bge-m3 model pass.

---

## Prerequisites

| Tool | Why |
|------|-----|
| Python 3.12+ | Required by the package |
| [uv](https://docs.astral.sh/uv/) | Dependency and virtualenv management |
| Docker + Docker Compose | Runs the local Qdrant instance |
| `make` | Wraps every common workflow |

---

## Quick start (5 minutes)

```bash
git clone https://github.com/nelsonfrugeri-tech/oh-my-kb.git
cd oh-my-kb
make install                          # uv sync — creates .venv
docker compose up -d                  # start Qdrant on localhost:6333
omk install                           # provision the default universe
omk bootstrap --harness claude-code   # inject MCP rules into CLAUDE.md
```

After that, write your first note in Claude Code:

```
Use kb_write to record: we chose Qdrant as our vector store.
```

---

## Onboarding — step by step

### 1. omk install

```bash
make install          # creates .venv, installs all deps via uv
docker compose up -d  # starts Qdrant on localhost:6333
omk install           # idempotent: brings up Qdrant, caches bge-m3 model,
                      # creates the 'default' universe at ~/oh-my-kb/default/
```

`omk install` prints what it provisioned:

```
Provisioned:
  qdrant     : http://localhost:6333
  universe   : default (active)
  notes dir  : /Users/you/oh-my-kb/default
  collection : kb_default
  config     : /Users/you/.config/oh-my-kb/config.toml
```

The first run downloads ~2 GB of bge-m3 model weights into `~/.cache/huggingface`. Subsequent runs reuse the cache — model loading adds roughly 5 seconds to the first MCP request.

### 2. Wire the MCP server

**Option A — `omk bootstrap` (recommended)**

```bash
omk bootstrap --harness claude-code   # injects the kb-mcp rules block into CLAUDE.md
```

This writes the MCP server entry and a usage rules block for all five tools into your project's `CLAUDE.md`. It is idempotent — re-running replaces the block in place.

**Option B — manual configuration**

```bash
claude mcp add o-kb-mcp -- uv run o-kb-mcp
```

Then add a rules block to your `CLAUDE.md`:

```
## oh-my-kb — knowledge base rules

Before answering any question that may be covered by the knowledge base:
1. Call kb_search with a natural-language query (or kb_tree for structural exploration).
2. Call kb_expand on any promising hit to read the full note body.
3. Call kb_recent when the question is about recency or time windows.
4. Call kb_write to record every significant decision, event, or procedure.

Read skill://scribe/SKILL.md before every kb_write call.
```

### 3. Write the first note

In your AI session:

```
Use kb_write to record: we decided to use PostgreSQL for transactional data and
Qdrant for vector search. PostgreSQL handles the source-of-truth records;
Qdrant holds embeddings for semantic retrieval. SQLite was ruled out due to
lack of concurrent writes in production.
```

The harness calls `kb_write` and the note appears under `~/oh-my-kb/default/`.

### 4. Search and navigate

```
What do we know about our database stack?
```

The harness calls `kb_search`, finds the note by semantic similarity, then calls `kb_expand` to read the full body.

---

## Concepts

### Notes

Every note has:
- A UUID `id` assigned on creation.
- A `type`: `decision`, `event`, `procedure`, `reference`, or `conversation`.
- A `project` grouping (arbitrary string, used for navigation via `kb_tree`).
- A `universe` declaring which isolated knowledge domain it belongs to.
- A `summary` (200–800 chars) — the text that is embedded for search.
- A `body` — full markdown content, not indexed.
- Optional `links_out`: a list of note UUIDs this note references.
- Optional `supersedes`: the UUID of the note this one replaces (the old note is archived).
- `archived`: boolean — archived notes are excluded from search unless explicitly requested.

Notes are stored as markdown files with YAML frontmatter. The frontmatter carries all structured fields; the body follows as free-form markdown.

### Universes

A universe is an isolated knowledge domain: one Qdrant collection (`kb_<slug(name)>`) plus one directory of markdown files (`~/oh-my-kb/<name>/`). Search never crosses universe boundaries — isolation is at the collection level.

```bash
omk universe create work              # create a new universe
omk universe list                     # list all universes (* = active)
omk universe use work                 # switch active universe
```

Config lives at `~/.config/oh-my-kb/config.toml`. Note data lives under `~/oh-my-kb/<universe>/` — visible, not a dotfile, easy to open in an editor or commit to git.

### Hybrid search

Each note's summary is embedded by bge-m3 in a single forward pass that produces:
- A 1024-dim dense vector for semantic similarity.
- A lexical sparse vector for keyword precision.

Qdrant fuses both ranked candidate lists using Reciprocal Rank Fusion (RRF) server-side. Filters (`project`, `archived`) are pushed down as payload conditions before fusion. This means you get semantic recall without losing exact-match precision.

---

## CLI reference — omk

```
omk [COMMAND]
```

| Command | What it does |
|---------|-------------|
| `omk install` | Provision Qdrant, cache bge-m3, create `default` universe. Idempotent. |
| `omk help` | Show available commands with a one-line description each. |
| `omk universe create <name> [--notes-root PATH]` | Create a universe: directory + Qdrant collection + config entry. |
| `omk universe list` | List configured universes. Active universe is marked with `*`. |
| `omk universe use <name>` | Set the named universe as active. |
| `omk bootstrap --harness <harness>` | Inject kb-mcp rules into the harness's rules file. Idempotent. |
| `omk reindex [--universe NAME]` | Reconcile Qdrant with markdown files on disk. See path discipline section. |

Exit codes: `0` for success, `1` for configuration errors (no active universe, unknown universe, Qdrant unreachable).

---

## MCP tools reference — o-kb-mcp

Five tools are exposed by the MCP server (`uv run o-kb-mcp`):

| Tool | Purpose |
|------|---------|
| `kb_write` | Record a new note (decision, event, procedure, reference, or conversation). Embeds and indexes immediately. |
| `kb_search` | Semantic hybrid search across the active universe. Returns ranked results with score. |
| `kb_recent` | Recall notes by creation time window with optional topic re-ranking. |
| `kb_tree` | Return a structural map of the universe grouped by project. No file reads. |
| `kb_expand` | Open a specific note in full and resolve its `links_out` to linked note payloads. |

### Navigate vs. search vs. recent

- **`kb_search`** — use when you have a topic or question and want the most semantically relevant notes regardless of when they were created.
- **`kb_tree`** — use when you want a bird's-eye view of what exists, grouped by project. Efficient: reads only Qdrant payloads, no disk access.
- **`kb_expand`** — use after `kb_search` or `kb_tree` to read the full body of a note and follow one hop of the knowledge graph.
- **`kb_recent`** — use when recency matters: "last 7 days", "latest decisions on project X". Supports an optional `topic` for semantic ranking within the time window.

Accepted `since` formats for `kb_recent`:

| Format | Example |
|--------|---------|
| Relative days | `"7d"` |
| Relative weeks | `"2w"` |
| Relative hours | `"24h"` |
| Relative minutes | `"90m"` |
| ISO date | `"2026-06-01"` |
| ISO datetime (tz-aware) | `"2026-06-01T00:00:00+00:00"` |

The MCP server also exposes two skill resources the harness can read before writing notes:
- `skill://scribe/SKILL.md` — when to create vs. supersede, how to pick `type`, how to write a retrieval-effective summary, how to extract `entities` and discover `links_out`.
- `skill://scribe/template.md` — the required body structure per note type.

Server-side validation enforces a summary length of 200–800 chars and rejects summaries identical to the title; violations return a clear tool error.

---

## Filesystem and config conventions

```
oh-my-kb/              # repository root
  oh_my_kb/
    core/              # pure domain: Note model, serialization, slug
    storage/           # Qdrant adapter (QdrantStore, IN_MEMORY sentinel)
    embedding/         # bge-m3 via FlagEmbedding (abstract Embedder interface)
    services/          # Indexer, SearchService, NavigationService, RecentService, ReindexService
    cli/               # omk CLI (install, universe, bootstrap, reindex)
    mcp/
      server.py        # MCP entry point (o-kb-mcp)
      tools/           # kb_write, kb_search, kb_tree, kb_expand, kb_recent
      skills/          # scribe playbook (SKILL.md + template.md)
  tests/
  docs/
    adr/               # architecture decision records
  docker-compose.yml
  Makefile
```

User data directories:

| Path | Contents |
|------|----------|
| `~/.config/oh-my-kb/config.toml` | Universe registry, active universe pointer |
| `~/oh-my-kb/<universe>/` | Markdown note files |
| `~/.cache/huggingface/` | bge-m3 model weights (~2 GB, downloaded once) |

---

## Path discipline and omk reindex

The Indexer keeps Qdrant and disk in sync when notes are written through `kb_write`. If you move or rename `.md` files manually (for example to reorganise project directories), the Qdrant payload will have a stale `path` field.

Run `omk reindex` to reconcile:

```bash
omk reindex                    # reindex the active universe
omk reindex --universe work    # reindex a specific universe
```

What it does:

1. Scans every `.md` file under the universe's notes directory (recursively).
2. Parses each file, re-embeds its summary using bge-m3, and upserts the Qdrant point with the **current file path** — correcting any stale entries.
3. Removes Qdrant points whose `.md` no longer exists on disk (orphan cleanup).

`omk reindex` is **fully idempotent**: running it twice in a row produces the same Qdrant state. The second run reports `removed=0`.

The filesystem is the source of truth for which notes exist: if a file is on disk it gets indexed; if a Qdrant point exists but the file is gone the point is removed.

---

## Running tests

```bash
make test                       # full test suite
uv run pytest -m "not slow"    # fast loop — skips the real bge-m3 load (~2 s)
uv run pytest -m slow          # slow tests only (loads bge-m3, ~5 s warm-up)
uv run pytest tests/test_smoke_e2e.py -v   # explicit smoke test
make check                     # CI gate: ruff lint + mypy + pytest
```

Test layers:

- **Unit and integration tests** use `QdrantStore(':memory:')` and `StubEmbedder` — no Docker, no network, no model. Runs in under 2 seconds.
- **Slow tests** (`@pytest.mark.slow`) load the real bge-m3 model and exercise the full end-to-end pipeline: index → search → tree → expand → supersede → reindex. The first run downloads model weights; subsequent runs use the `~/.cache/huggingface` cache.

---

## Architecture

Domain logic lives in `oh_my_kb/core/` with no MCP, CLI, or network dependencies. The MCP server (`oh_my_kb/mcp/`) and CLI (`oh_my_kb/cli/`) are thin adapters, so the same services are reachable from any future SDK or automation layer.

Hybrid retrieval uses bge-m3 to produce a 1024-dim dense vector and a sparse lexical vector from a single model pass. Qdrant fuses the two ranked candidate lists using Reciprocal Rank Fusion server-side. Filters (`project`, `archived`) are pushed down as payload conditions before fusion.

Each universe maps to one Qdrant collection (`kb_<slug(universe)>`). Search never crosses universe boundaries — isolation is at the collection level.

For detailed architectural decisions, see `docs/adr/`.

---

## Local infrastructure (Qdrant)

Qdrant runs locally via Docker Compose:

```bash
docker compose up -d      # start Qdrant (localhost:6333)
docker compose down       # stop Qdrant
docker compose down -v    # stop and remove all data volumes
```

`docker-compose.yml` in the repo root defines the Qdrant service. The default URL is `http://localhost:6333` and is overridable via the `KB_QDRANT_URL` environment variable (used by tests with the `:memory:` in-process backend).

---

## Troubleshooting

**`omk install` fails with "Qdrant unreachable"**

Ensure Docker is running and Qdrant started successfully:

```bash
docker compose up -d
docker compose ps         # check Qdrant is healthy
```

**`kb_write` or search returns an error about no active universe**

Run `omk install` (first time) or `omk universe use <name>` to set an active universe.

**Notes are missing from search after moving `.md` files manually**

Run `omk reindex` to reconcile the Qdrant index with the current filesystem state.

**First MCP request is slow (~5 seconds)**

The bge-m3 model is loaded from disk on the first request. Subsequent requests within the same server session are fast. Model weights are cached at `~/.cache/huggingface/`.

**mypy reports errors in `oh_my_kb/cli/app.py` or `oh_my_kb/mcp/server.py`**

These errors are pre-existing and caused by missing stubs for `typer` and the MCP SDK. They do not affect runtime behaviour. All 15 mypy errors are in files unrelated to the reindex implementation.

---

## License

See [LICENSE](LICENSE).
