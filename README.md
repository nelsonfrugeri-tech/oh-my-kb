# oh-my-harness

Personal AI harness: persistent knowledge base (MCP) and versioned skills/agents manager
for Claude Code and other AI assistants.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

---

## What it is

AI assistants have no persistent memory across sessions and no standard way to carry
domain-specific knowledge — prompting patterns, architecture decisions, team conventions —
from one project to the next.

oh-my-harness solves this in two layers:

**Knowledge base (o-kb-mcp).** Notes are written as Markdown files, embedded with BGE-M3,
and stored in Qdrant. A Model Context Protocol server exposes five tools that Claude can
invoke to write, search, navigate, and recall notes without any manual retrieval step.
The knowledge base persists across sessions, projects, and machines.

**Skills and agents (omh cli).** A curated set of 17 skills and 6 agents lives in this
repository as versioned `.md` files. The `omh skills` and `omh agents` commands pull them
into `~/.claude/` where Claude Code picks them up automatically. SemVer + sha256 checksums
in a manifest file make drift detection and incremental updates precise.

```
git clone https://github.com/nelsonfrugeri-tech/oh-my-harness.git
cd oh-my-harness
make install
uv run omh install          # interactive wizard, ~2 min

uv run omh status           # verify everything is running
uv run omh skills list      # 17 skills, all up-to-date
uv run omh agents list      # 6 agents, all up-to-date
```

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Install wizard](#install-wizard)
- [What omh install does](#what-omh-install-does)
- [CLI reference](#cli-reference)
- [Versioning model](#versioning-model)
- [Manifest format](#manifest-format)
- [MCP tools](#mcp-tools)
- [Environment variables](#environment-variables)
- [Configuration files](#configuration-files)
- [How to extend](#how-to-extend)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

- **MCP server with 5 knowledge-base tools** — `kb_write`, `kb_search`, `kb_tree`,
  `kb_expand`, `kb_recent`. Knowledge interaction stays in MCP; the CLI manages
  infrastructure and assets.
- **Hybrid search** — BGE-M3 dense embeddings + RRF fusion in Qdrant for high-recall
  semantic retrieval.
- **Skills and agents versioned as API contracts** — SemVer + sha256 per file in a
  manifest. PATCH/MINOR/MAJOR carry well-defined compatibility guarantees.
- **Interactive install wizard** — one command configures Qdrant, creates the knowledge
  base, injects rules into `~/.claude/CLAUDE.md`, and downloads all 17 skills and 6 agents.
- **Incremental update loop** — `omh skills diff` / `omh agents diff` detect drift by
  comparing local sha256 against the manifest. `omh skills update` applies only what
  changed and prompts before applying MAJOR (breaking) version bumps.
- **Multi-knowledge-base support** — create and switch between named knowledge bases
  with `omh kb create` / `omh kb use`.
- **Non-interactive mode** — `omh install --yes` accepts all defaults for scripted or
  CI use.

---

## Architecture

```
+--------------------+        MCP (stdio)        +---------------------+
|   Claude Code      | <-----------------------> |   o-kb-mcp server   |
|  (or any harness)  |    kb_write / kb_search   |  BGE-M3 + Qdrant    |
+--------------------+    kb_tree / kb_expand    +---------------------+
                          kb_recent                        |
                                                  +--------+--------+
                                                  |  Qdrant (Docker)|
                                                  |  localhost:6333 |
                                                  +-----------------+

+--------------------+        HTTPS              +---------------------+
|   omh CLI          | <-----------------------> | raw.githubusercontent|
|  skills / agents   |  assets/manifest.json     |  assets/skills/     |
|  kb / lifecycle    |  assets/skills/*.md        |  assets/agents/     |
+--------------------+  assets/agents/*.md        +---------------------+
         |
         v
~/.claude/skills/<name>/SKILL.md
~/.claude/agents/<name>.md
~/.claude/CLAUDE.md  (rules block injected by omh install)
```

The MCP server and the CLI are independent entry points from the same package.
Skills and agents are NOT fetched via MCP — the CLI pulls them directly over HTTPS
from `raw.githubusercontent.com`. This keeps the MCP surface minimal and avoids
bundling distribution logic into the server.

---

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Tested on 3.12 |
| [uv](https://docs.astral.sh/uv/) | latest | Package manager and task runner |
| Docker Desktop | any recent | Must be running before `omh install` |
| make | any | Wraps uv commands |

---

## Quick start

```bash
git clone https://github.com/nelsonfrugeri-tech/oh-my-harness.git
cd oh-my-harness
make install          # creates .venv and installs all dependencies via uv sync
uv run omh install    # interactive wizard
```

The wizard asks 5 questions (all have working defaults — press Enter to accept each).
After it completes, open Claude Code in any project. The knowledge-base tools and all
17 skills + 6 agents are active immediately.

To verify:

```bash
uv run omh status
uv run omh kb list
uv run omh skills list
uv run omh agents list
```

To run non-interactively:

```bash
uv run omh install --yes
```

---

## Install wizard

The wizard collects 5 configuration values, then runs 8 automated steps.

| # | Question | Default |
|---|----------|---------|
| 1 | Notes storage directory | `~/oh-my-harness` |
| 2 | Knowledge base name | `default` |
| 3 | Qdrant port | `6333` |
| 4 | Models cache directory | `~/.cache/oh-my-harness/models` |
| 5 | AI harness to configure | `claude-code` |

After confirming the summary, the wizard proceeds to the 8 automated steps.

---

## What `omh install` does

1. **[1/8] Verify Docker** — checks Docker daemon is running; exits with a clear error
   if not.
2. **[2/8] Start Qdrant** — pulls `qdrant/qdrant:latest` if not cached and starts the
   container on the configured port. Idempotent: if the container is already running,
   this step is a no-op.
3. **[3/8] Create knowledge base directory** — creates `<notes_root>/<name>/` on disk.
4. **[4/8] Save configuration** — writes `~/.config/oh-my-harness/config.toml` with
   core settings (notes root, active knowledge base, models cache), Qdrant connection,
   and active harness. Also creates the Qdrant collection for the new knowledge base.
5. **[5/8] Generate rules block** — renders the `o-kb-mcp` rules Markdown block with
   the knowledge base name and manifest URL interpolated.
6. **[6/8] Inject rules into `~/.claude/CLAUDE.md`** — bootstraps the harness by
   inserting the rules block between idempotent marker comments. Re-running install
   updates the block in place without duplicating it.
7. **[7/8] Write user preferences section** — detects OS and hostname, writes a
   `## User Preferences` section to `~/.claude/CLAUDE.md` under separate markers.
   Idempotent: a second run leaves the section unchanged if nothing changed.
8. **[8/8] Download skills and agents** — fetches all 17 skills and 6 agents from the
   remote manifest into `~/.claude/skills/` and `~/.claude/agents/`. Network failures
   in this step are non-fatal: install exits 0 and prints a hint to run
   `omh skills pull --all` manually.

---

## CLI reference

### Lifecycle

```
omh install [--yes]               Interactive setup wizard (--yes accepts all defaults)
omh start                         Start the Qdrant Docker container (idempotent)
omh stop                          Stop the Qdrant Docker container
omh status                        Show system state: Qdrant health, active knowledge base
omh reindex [--kb NAME]           Reconcile Qdrant collection with markdown files on disk
```

### Knowledge bases

```
omh kb create <name> [--notes-root PATH]   Create a new knowledge base
omh kb list                                List configured knowledge bases (* = active)
omh kb use <name>                          Set the active knowledge base
```

### Skills

```
omh skills list                    List skills with local version, remote version, status
omh skills pull <name>             Download a single skill to ~/.claude/skills/<name>/
omh skills pull --all              Download all 17 skills
omh skills diff [<name>]           Compare local sha256 against manifest (all or one)
omh skills update [<name>]         Update skills that are not up-to-date
omh skills update [<name>] --yes   Update without confirmation prompt
```

Status values reported by `list` and `diff`:

| Status | Meaning |
|--------|---------|
| `up-to-date` | Local sha256 matches the manifest |
| `not-installed` | Skill directory does not exist locally |
| `drift` | sha256 mismatch (content changed or version bumped) |
| `drift  [BREAKING]` | Major version increased — update will change behavior |

### Agents

```
omh agents list                    List agents with local version, remote version, status
omh agents pull <name>             Download a single agent to ~/.claude/agents/<name>.md
omh agents pull --all              Download all 6 agents
omh agents diff [<name>]           Compare local sha256 against manifest
omh agents update [<name>]         Update agents that are not up-to-date
omh agents update [<name>] --yes   Update without confirmation prompt
```

### Workflows

```
omh workflows list                  List workflows with local version, remote version, status
omh workflows pull <name>           Download a workflow to ~/.claude/workflows/<name>.ts
omh workflows pull --all            Download all workflows
omh workflows diff [<name>]         Compare local sha256 against manifest
omh workflows update [<name>]       Update workflows that are not up-to-date
omh workflows update [<name>] --yes Update without confirmation prompt
```

### Auto-dependency resolution

`omh skills pull`, `omh agents pull`, and `omh workflows pull` automatically resolve and
download the full transitive dependency closure before downloading the requested asset:

- **workflow** pull → downloads every referenced agent and each agent's declared skills
- **agent** pull → downloads every skill listed in the agent's YAML frontmatter `skills:`
- **skill** pull → skills are leaf nodes; no further dependencies

The order is always topological: skills first, then agents, then workflows.  Duplicate
entries are deduplicated — if two agents share a skill, that skill is downloaded once.

To opt out of automatic dependency resolution and download only the named asset, pass
`--no-deps`:

```
omh workflows pull --no-deps create-feature   # workflow file only, no agents or skills
omh agents pull --no-deps developer           # agent file only, no skills
```

Dependencies are declared in `assets/manifest.json` (auto-generated by `make manifest`):

```json
{
  "workflows": [{"name": "create-feature", "dependencies": {"agents": ["tech_pm", "developer", "qa", "sre", "ai-engineer"]}}],
  "agents":    [{"name": "developer",      "dependencies": {"skills": ["implement", "test", "research", "review", "environment", "ai-engineer"]}}],
  "skills":    [{"name": "implement"}]
}
```

---

## Versioning model

Skills and agents are versioned with SemVer (`MAJOR.MINOR.PATCH`) and treated as
API contracts for AI workflows.

| Bump | When | Compatibility |
|------|------|---------------|
| `PATCH` (`1.0.x`) | Typo fixes, clarifications, non-semantic edits | Fully backward compatible |
| `MINOR` (`1.x.0`) | New sections, examples, additional guidance | Backward compatible |
| `MAJOR` (`x.0.0`) | Structural changes, removed sections, changed behavior | Breaking |

`omh skills update` and `omh agents update` detect MAJOR bumps by comparing the leading
integer of the local version (read from the YAML frontmatter of the installed `.md`) with
the remote version in the manifest. When a MAJOR bump is detected and `--yes` is not
given, the command prints a warning and asks for confirmation before proceeding.

The manifest stores a sha256 hash for every file. This allows `diff` to detect content
drift independently of version strings — useful for detecting silent local modifications
or out-of-band changes.

---

## Manifest format

`assets/manifest.json` is the single source of truth for the remote asset distribution.

```json
{
  "schema_version": 1,
  "skills": [
    {
      "name": "python",
      "version": "1.0.0",
      "path": "assets/skills/python",
      "files": [
        {
          "path": "SKILL.md",
          "sha256": "abc123..."
        },
        {
          "path": "references/typing.md",
          "sha256": "def456..."
        }
      ]
    }
  ],
  "agents": [
    {
      "name": "developer",
      "version": "1.0.0",
      "path": "assets/agents/developer.md",
      "sha256": "789abc..."
    }
  ]
}
```

Skills are multi-file (a directory with `SKILL.md` and optional `references/` files).
Agents are single-file. Every file entry carries its own sha256 so drift is detectable
at the file level.

The manifest is fetched fresh on every command invocation over HTTPS from
`raw.githubusercontent.com/nelsonfrugeri-tech/oh-my-harness/master/assets/manifest.json`.
No local caching — every `diff` or `update` call reflects the current remote state.

---

## MCP tools

The `o-kb-mcp` server registers exactly five tools. The knowledge base scope is fixed at
server start via the `KB_NAME` environment variable; tool calls cannot override it.

| Tool | Natural-language trigger |
|------|--------------------------|
| `kb_write` | User asks to save, record, document, or annotate something |
| `kb_search` | User asks to find, search, or remember something |
| `kb_tree` | User asks for an overview, map, or structure of the knowledge base |
| `kb_expand` | User wants to read a note in full or follow its outbound links |
| `kb_recent` | User asks for recent notes, latest decisions, or what changed recently |

`omh install` configures the MCP server automatically for the `claude-code` harness by
injecting the connection block into `~/.claude/CLAUDE.md`.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KB_NAME` | `default` | Knowledge base name bound to the running MCP server |
| `KB_QDRANT_URL` | `http://localhost:6333` | Qdrant HTTP endpoint |
| `OMH_CONFIG_DIR` | `~/.config/oh-my-harness` | Override the config directory (useful for isolated tests) |

---

## Configuration files

| Path | Written by | Purpose |
|------|------------|---------|
| `~/.config/oh-my-harness/config.toml` | `omh install` / `omh kb create` | Knowledge bases, active selection, Qdrant settings |
| `~/.claude/CLAUDE.md` | `omh install` | Rules block for `o-kb-mcp` tools + user preferences section |
| `~/.claude/skills/<name>/SKILL.md` | `omh skills pull` | Skill content used by Claude Code |
| `~/.claude/agents/<name>.md` | `omh agents pull` | Agent definitions used by Claude Code |

The `~/.claude/CLAUDE.md` file is managed with idempotent marker comments so repeated
installs or updates replace only the managed sections, leaving any user content outside
those markers untouched.

---

## How to extend

### Contributing a new skill or agent

1. Add the `.md` file(s) under `assets/skills/<name>/` (skill) or
   `assets/agents/<name>.md` (agent).
2. Every `.md` must start with a YAML frontmatter block containing at least
   `version: 1.0.0`.
3. Update `assets/manifest.json`:
   - Add an entry for the new skill or agent.
   - Compute sha256 per file: `shasum -a 256 <file>`.
   - Set `version: "1.0.0"`.
4. For changes to existing skills or agents, bump the version in both the frontmatter
   and the manifest following the PATCH/MINOR/MAJOR semantics above, and recompute sha256.
5. Open a pull request. A formal `CONTRIBUTING.md` is planned; open an issue to discuss
   significant changes before submitting.

---

## Roadmap

- **PyPI release** — `pip install oh-my-harness` / `uvx omh install`.
- **`omh` commands as MCP tools** — so Claude Code can invoke `omh skills update` or
  `omh kb use` via natural language without leaving the chat.
- **Additional harness support** — VS Code Copilot, Cursor, and other harnesses that
  support a skills/agents directory convention.
- **Drop the `universe` compat shims** — `KB_UNIVERSE` env var, `default_universe` TOML
  key, `--universe` reindex flag, and function/class aliases (`add_universe`,
  `NoActiveUniverseError`, etc.) are kept as silent fallbacks for backward compatibility.
  Remove them in a future major version once no installations rely on them.

---

## License

Apache License 2.0. See [LICENSE](LICENSE).
