# oh-my-kb

Their knowledge is their universe. A programmatic, agnostic knowledge base exposed via MCP, with markdown notes indexed in Qdrant for hybrid search.

## Architecture

Domain logic lives in `oh_my_kb/core/` with no MCP, CLI, or network dependencies. The MCP server (`oh_my_kb/mcp/`) and CLI (`oh_my_kb/cli/`) are thin adapters over `core`, so a future `o-kb-sdk` can reuse the same logic.

```
oh_my_kb/
  core/       # pure domain logic — no MCP / CLI / network
  storage/    # infrastructure adapters (Qdrant)
  embedding/  # embedding interface + bge-m3 implementation
  services/   # application services (Indexer) — orchestrate core/storage/embedding
  mcp/        # MCP server adapter
  cli/        # CLI adapter
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

- **Filesystem layout:** `<KB_NOTES_ROOT>/<slug(universe)>/<slug(project)>/<note.slug>.md`. `KB_NOTES_ROOT` defaults to `~/kb`.
- **Collection naming:** one Qdrant collection per universe, named `kb_<slug(universe)>`. Search never crosses universes.
- **Indexed payload:** the note's identity + the absolute path to the file. The full body is **not** stored in Qdrant — it lives on disk and is read back via the payload's `path` when needed.
