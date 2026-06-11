# oh-my-harness

Personal AI harness: a long-term knowledge base (MCP) + skill and agent management CLI
for Claude Code and other AI assistants.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — package manager
- Docker Desktop (running)
- make

## Quick start

```bash
git clone https://github.com/nelsonfrugeri-tech/oh-my-kb.git
cd oh-my-kb
make install
uv run omh install
```

The install wizard walks through 5 questions and then sets everything up automatically.

## Install wizard

| Step | Question | Default |
|------|----------|---------|
| 1 | Notes directory | ~/oh-my-harness |
| 2 | Universe name | default |
| 3 | Qdrant port | 6333 |
| 4 | Models cache directory | ~/.cache/oh-my-harness/models |
| 5 | AI harness | claude-code |

Non-interactive mode: `uv run omh install --yes`

## What install does

After confirming your choices, install runs 8 steps:

1. Verifies Docker is running
2. Starts Qdrant vector database container
3. Creates the universe notes directory
4. Saves configuration to `~/.config/oh-my-harness/`
5. Generates the kb-mcp rules block
6. Injects the rules block into `~/.claude/CLAUDE.md`
7. Writes the User Preferences section
8. Downloads all skills and agents from the official manifest

After install you get:
- Qdrant running on `localhost:6333`
- `~/.claude/CLAUDE.md` configured with kb-mcp tools and harness rules
- Skills installed in `~/.claude/skills/<name>/`
- Agents installed in `~/.claude/agents/<name>.md`

## Verify

```bash
omh status            # Qdrant health and active universe
omh kb list           # configured knowledge bases
omh skills list       # installed skills vs remote versions
omh agents list       # installed agents vs remote versions
```

## CLI reference

### Lifecycle

```
omh install [--yes]   interactive setup wizard
omh start             start Qdrant container
omh stop              stop Qdrant container
omh status            show system state
omh reindex           sync Qdrant with notes on disk
```

### Knowledge bases

```
omh kb create <name>  create a new knowledge base
omh kb list           list configured knowledge bases
omh kb use <name>     switch active knowledge base
```

### Skills

```
omh skills list               list skills with versions and status
omh skills pull <name>        download a single skill
omh skills pull --all         download all skills
omh skills diff [<name>]      compare local vs remote sha256
omh skills update [<name>]    apply updates (prompts on BREAKING)
omh skills update --yes       update without confirmation
```

### Agents

```
omh agents list               list agents with versions and status
omh agents pull <name>        download a single agent
omh agents pull --all         download all agents
omh agents diff [<name>]      compare local vs remote sha256
omh agents update [<name>]    apply updates (prompts on BREAKING)
omh agents update --yes       update without confirmation
```

## Versioning

Skills and agents use SemVer (`major.minor.patch`).

- `MAJOR` bump — breaking change: existing workflows may need updating.
  `omh skills update` and `omh agents update` prompt for confirmation.
- `MINOR` bump — new content, backward compatible.
- `PATCH` bump — corrections and clarifications.

The manifest at `assets/manifest.json` contains the sha256 of every file.
`omh skills diff` compares local sha256 against the manifest to detect drift.

## MCP server tools

The `o-kb-mcp` server exposes five tools to Claude:

| Tool | Trigger |
|------|---------|
| `kb_write` | user asks to save, record or document something |
| `kb_search` | user asks to find or remember something |
| `kb_tree` | user asks for an overview or map of knowledge |
| `kb_expand` | user wants to read a note in full or follow links |
| `kb_recent` | user asks for recent notes or history |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KB_UNIVERSE` | (active from config) | Universe bound to the MCP server |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant endpoint |
| `OMH_CONFIG_DIR` | `~/.config/oh-my-harness` | Config directory override |

## Coming soon

- PyPI package (`pip install oh-my-harness`)
- `omh` tools exposed as MCP tools for agent-to-agent calls
