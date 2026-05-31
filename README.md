# oh-my-kb

Their knowledge is their universe. A programmatic, agnostic knowledge base exposed via MCP, with markdown notes indexed in Qdrant for hybrid search.

## Architecture

Domain logic lives in `oh_my_kb/core/` with no MCP, CLI, or network dependencies. The MCP server (`oh_my_kb/mcp/`) and CLI (`oh_my_kb/cli/`) are thin adapters over `core`, so a future `o-kb-sdk` can reuse the same logic.

```
oh_my_kb/
  core/   # pure domain logic — no MCP / CLI / network
  mcp/    # MCP server adapter
  cli/    # CLI adapter
tests/
```

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- `make`

## Usage

All workflows are wrapped by `make`. Run `make` (or `make help`) to list every target.

```bash
make venv       # create .venv and install all dependencies (uv sync)
make test       # run the test suite (uv run pytest)
make lint       # lint with ruff
make format     # format with ruff
make typecheck  # type-check with mypy
make check      # lint + typecheck + test (the CI gate)
make clean      # remove .venv and tool caches
```
