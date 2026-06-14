<div align="center">

# oh-my-harness

**The meta-harness that turns any AI assistant into a high-performance engineering partner.**

A provider-agnostic superpower layer — persistent knowledge, versioned skills, expert agents, and standardized workflows — all in one open-source toolkit.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-4CAF50?style=flat-square)](LICENSE)
[![uv](https://img.shields.io/badge/package%20manager-uv-5B4FE4?style=flat-square)](https://docs.astral.sh/uv/)
[![Qdrant](https://img.shields.io/badge/vector%20db-Qdrant-DC143C?style=flat-square)](https://qdrant.tech/)

</div>

---

## The problem with AI assistants today

Every new session starts from zero. Your conventions, your architecture decisions, your team standards — gone. You paste the same context over and over, explain the same patterns, correct the same mistakes. The assistant is powerful but stateless, generic but not yours.

**oh-my-harness changes that.**

It is a **meta-harness**: a software layer that sits above any AI assistant (Claude Code, Cursor, Copilot, and more) and enriches it with four capabilities that don't exist out of the box:

| Capability | What it means |
|---|---|
| **Persistent knowledge base** | Notes, decisions, and patterns survive across sessions, projects, and machines |
| **Versioned skill library** | 20+ curated domain skills injected directly into the assistant's context |
| **Expert agent roster** | Role-specific agents (developer, architect, QA, SRE, tech PM...) with declared skill dependencies |
| **Standardized workflows** | Multi-agent pipelines (feature creation, code review, validation) with transitive dependency resolution |

The result: an assistant that knows your universe, speaks your language, and gets smarter the longer you use it.

---

## Table of contents

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [What `omh install` does](#what-omh-install-does)
- [CLI reference](#cli-reference)
- [Auto-dependency resolution](#auto-dependency-resolution)
- [Knowledge base — MCP tools](#knowledge-base--mcp-tools)
- [Versioning model](#versioning-model)
- [Manifest format](#manifest-format)
- [Environment variables](#environment-variables)
- [Configuration files](#configuration-files)
- [How to extend](#how-to-extend)
- [Roadmap](#roadmap)
- [License](#license)

---

## How it works

oh-my-harness has two independent layers that work together:

```
┌─────────────────────────────────────────────────────────────────┐
│                        YOUR AI ASSISTANT                        │
│               (Claude Code · Cursor · Copilot · ...)            │
└──────────────────────┬──────────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          │                         │
  ┌───────▼────────┐      ┌─────────▼────────────┐
  │  o-kb-mcp      │      │  omh CLI             │
  │  MCP server    │      │  asset manager       │
  │                │      │                      │
  │  kb_write      │      │  skills  pull/update │
  │  kb_search     │      │  agents  pull/update │
  │  kb_tree       │      │  workflows pull/upd  │
  │  kb_expand     │      │  kb      create/use  │
  │  kb_recent     │      │  install/start/stop  │
  └───────┬────────┘      └─────────┬────────────┘
          │                         │
  ┌───────▼────────┐      ┌─────────▼────────────┐
  │  Qdrant        │      │  raw.githubusercontent│
  │  BGE-M3 embeds │      │  assets/manifest.json │
  │  localhost:6333│      │  skills · agents      │
  └────────────────┘      │  workflows            │
                          └──────────────────────┘
                                    │
                          ┌─────────▼────────────┐
                          │  ~/.claude/          │
                          │  skills/<name>/      │
                          │  agents/<name>.md    │
                          │  workflows/<name>.ts │
                          │  CLAUDE.md           │
                          └──────────────────────┘
```

**Layer 1 — Knowledge base (`o-kb-mcp`)**
Notes are written as Markdown, embedded with BGE-M3, and stored in Qdrant. An MCP server exposes five tools the assistant calls automatically. Knowledge persists across sessions, projects, and machines — the assistant remembers what you've built and decided.

**Layer 2 — Asset manager (`omh`)**
A CLI that pulls versioned skills, agents, and workflows from this repository into `~/.claude/`. SemVer + sha256 checksums in a manifest file make drift detection and incremental updates precise. Pulling a workflow automatically resolves and downloads every agent and skill it depends on — one command, zero manual dependency hunting.

---

## Quick start

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker Desktop

```bash
git clone https://github.com/nelsonfrugeri-tech/oh-my-harness.git
cd oh-my-harness
make install          # creates .venv, installs all dependencies
uv run omh install    # interactive setup wizard (~2 min)
```

The wizard asks five questions — all have sensible defaults, press Enter to accept each. When it finishes, open Claude Code in any project. The knowledge-base tools and the full skill + agent library are active immediately.

```bash
uv run omh status           # verify everything is running
uv run omh skills list      # 20 skills, all up-to-date
uv run omh agents list      # 9 agents, all up-to-date
uv run omh workflows list   # published workflows
```

To run without any prompts (scripted / CI):

```bash
uv run omh install --yes
```

---

## Install wizard

The wizard collects five configuration values, then runs eight automated steps.

| # | Question | Default |
|---|----------|---------|
| 1 | Notes storage directory | `~/oh-my-harness` |
| 2 | Knowledge base name | `default` |
| 3 | Qdrant port | `6333` |
| 4 | Models cache directory | `~/.cache/oh-my-harness/models` |
| 5 | AI harness to configure | `claude-code` |

---

## What `omh install` does

1. **[1/8] Verify Docker** — checks Docker daemon is running; exits with a clear error if not.
2. **[2/8] Start Qdrant** — pulls `qdrant/qdrant:latest` if not cached and starts the container on the configured port. Idempotent: if already running, this step is a no-op.
3. **[3/8] Create knowledge base directory** — creates `<notes_root>/<name>/` on disk.
4. **[4/8] Save configuration** — writes `~/.config/oh-my-harness/config.toml` with core settings, Qdrant connection, and active harness. Creates the Qdrant collection for the new knowledge base.
5. **[5/8] Generate rules block** — renders the `o-kb-mcp` rules Markdown block with the knowledge base name and manifest URL interpolated.
6. **[6/8] Inject rules into `~/.claude/CLAUDE.md`** — bootstraps the harness by inserting the rules block between idempotent marker comments. Re-running install updates the block in place without duplicating it.
7. **[7/8] Write user preferences** — detects OS and hostname, writes a `## User Preferences` section to `~/.claude/CLAUDE.md` under separate markers. Idempotent.
8. **[8/8] Download skills, agents, and workflows** — fetches all assets from the remote manifest into `~/.claude/`. Network failures are non-fatal: install exits 0 and prints a hint to run `omh skills pull --all` manually.

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

Skills are curated domain-knowledge modules loaded directly into the assistant's context. Each skill is a directory with a `SKILL.md` entry point and optional `references/` files.

```
omh skills list                    List skills with local version, remote version, status
omh skills pull <name>             Download a skill (+ its dependencies) to ~/.claude/skills/
omh skills pull --all              Download all skills
omh skills pull --no-deps <name>   Download only the named skill, skip dependency resolution
omh skills diff [<name>]           Compare local sha256 against manifest (all or one)
omh skills update [<name>]         Update skills that are not up-to-date
omh skills update [<name>] --yes   Update without confirmation prompt
```

**Status values:**

| Status | Meaning |
|--------|---------|
| `up-to-date` | Local sha256 matches the manifest |
| `not-installed` | Skill directory does not exist locally |
| `drift` | sha256 mismatch — content changed or version bumped |
| `drift  [BREAKING]` | Major version increased — update will change behavior |

### Agents

Agents are role-specific AI personas. Each declares the skills it needs in its YAML frontmatter — pulling an agent automatically pulls its skill dependencies.

```
omh agents list                    List agents with local version, remote version, status
omh agents pull <name>             Download an agent (+ its skill deps) to ~/.claude/agents/
omh agents pull --all              Download all agents (+ all skill deps)
omh agents pull --no-deps <name>   Download only the agent file, skip skill resolution
omh agents diff [<name>]           Compare local sha256 against manifest
omh agents update [<name>]         Update agents that are not up-to-date
omh agents update [<name>] --yes   Update without confirmation prompt
```

**Available agents:**

| Agent | Role | Key skills |
|-------|------|------------|
| `developer` | Senior software engineer | implement, test, environment, review, research, ai-engineer |
| `ai-engineer` | AI/ML specialist | ai-engineer, implement, test, environment, review, research |
| `architect` | System designer | design, review, research, api-design, security |
| `qa` | Quality assurance engineer | test, environment, review, research |
| `sre` | Site reliability engineer | operate, observability, security, review, research |
| `tech_pm` | Technical product manager | manage, review, research |
| `explorer` | Codebase analyst | design, api-design, ai-engineer, research, security |
| `context` | Context loader/updater | research |
| `startup_project` | Project initializer | manage, research |

### Workflows

Workflows are multi-agent pipelines defined as TypeScript files. They orchestrate agents across phases and carry full dependency metadata — pulling a workflow resolves and downloads every agent and skill in its transitive closure.

```
omh workflows list                  List workflows with local version, remote version, status
omh workflows pull <name>           Download a workflow (+ all agent + skill deps)
omh workflows pull --all            Download all workflows (+ full dependency graph)
omh workflows pull --no-deps <name> Download only the workflow file
omh workflows diff [<name>]         Compare local sha256 against manifest
omh workflows update [<name>]       Update workflows that are not up-to-date
omh workflows update [<name>] --yes Update without confirmation prompt
```

**Available workflows:**

| Workflow | Description |
|----------|-------------|
| `create-feature` | Full feature pipeline: user story (tech_pm) → implementation (developer/ai-engineer) → validation loop (qa + sre, up to 3 iterations) → pull request |

---

## Auto-dependency resolution

`omh skills pull`, `omh agents pull`, and `omh workflows pull` resolve the full transitive dependency closure before downloading — in topological order, leaves first.

```
omh workflows pull create-feature
#  pulling create-feature (5 agents + 10 skills as dependencies)
#    pulled skill implement (1 file)   [dep]
#    pulled skill test (1 file)        [dep]
#    pulled skill research (1 file)    [dep]
#    ...
#    pulled agent developer            [dep]
#    pulled agent qa                   [dep]
#    ...
#    pulled create-feature
```

**Dependency graph:**

```
workflow
  └─ agent (agentType: '...' in .ts source)
       └─ skill (skills: [...] in agent frontmatter)
```

- **workflow** pull → downloads every referenced agent and each agent's declared skills
- **agent** pull → downloads every skill listed in the agent's `skills:` frontmatter
- **skill** pull → skills are leaf nodes; no further dependencies

Duplicates are deduplicated automatically — if two agents share a skill, that skill is downloaded once.

To pull only the named asset without resolving dependencies:

```bash
omh workflows pull --no-deps create-feature   # workflow file only
omh agents pull --no-deps developer           # agent file only
```

Dependencies are declared in `assets/manifest.json`, auto-generated by:

```bash
make manifest   # runs scripts/build_manifest.py — idempotent, CI-friendly
```

---

## Knowledge base — MCP tools

The `o-kb-mcp` server exposes five tools the assistant calls automatically based on what you ask. The knowledge base scope is fixed at server start via `KB_NAME` — tool calls cannot override it.

| Tool | When the assistant uses it |
|------|---------------------------|
| `kb_write` | You ask to save, record, document, or annotate something |
| `kb_search` | You ask to find, search, or recall something |
| `kb_tree` | You ask for an overview, map, or structure of the knowledge base |
| `kb_expand` | You want to read a note in full or follow its outbound links |
| `kb_recent` | You ask for recent notes, latest decisions, or what changed recently |

`omh install` configures the MCP server for `claude-code` by injecting the connection block into `~/.claude/CLAUDE.md`. No manual configuration required.

---

## Versioning model

Skills, agents, and workflows are versioned with SemVer (`MAJOR.MINOR.PATCH`) and treated as API contracts for AI workflows.

| Bump | When | Compatibility |
|------|------|---------------|
| `PATCH` (`1.0.x`) | Typo fixes, clarifications, non-semantic edits | Fully backward compatible |
| `MINOR` (`1.x.0`) | New sections, examples, additional guidance | Backward compatible |
| `MAJOR` (`x.0.0`) | Structural changes, removed sections, changed behavior | Breaking |

`omh skills update` and `omh agents update` detect MAJOR bumps by comparing the leading integer of the local version (from the YAML frontmatter of the installed `.md`) with the remote version in the manifest. When a MAJOR bump is detected and `--yes` is not given, the command prints a warning and asks for confirmation before proceeding.

The manifest stores a sha256 hash for every file, enabling `diff` to detect content drift independently of version strings — useful for detecting silent local modifications or out-of-band changes.

---

## Manifest format

`assets/manifest.json` is the single source of truth for remote asset distribution.

```json
{
  "schema_version": 1,
  "skills": [
    {
      "name": "implement",
      "version": "1.0.0",
      "path": "assets/skills/implement",
      "files": [
        { "path": "SKILL.md", "sha256": "abc123..." }
      ]
    }
  ],
  "agents": [
    {
      "name": "developer",
      "version": "1.0.0",
      "path": "assets/agents/developer.md",
      "sha256": "def456...",
      "dependencies": {
        "skills": ["implement", "test", "environment", "review", "research", "ai-engineer"]
      }
    }
  ],
  "workflows": [
    {
      "name": "create-feature",
      "version": "1.0.0",
      "path": "assets/workflows/create-feature.ts",
      "sha256": "ghi789...",
      "dependencies": {
        "agents": ["tech_pm", "developer", "ai-engineer", "qa", "sre"]
      }
    }
  ]
}
```

- **Skills** are multi-file (directory with `SKILL.md` and optional `references/`). No `dependencies` field — skills are leaves.
- **Agents** are single `.md` files. Declare `dependencies.skills` from their YAML frontmatter `skills:` list.
- **Workflows** are single `.ts` files. Declare `dependencies.agents` extracted automatically from `agentType: '...'` string literals in the source.

The manifest is fetched fresh on every command invocation over HTTPS from `raw.githubusercontent.com`. No local caching — every `diff` or `update` call reflects the current remote state.

Rebuild the manifest locally after adding or editing assets:

```bash
make manifest   # idempotent — preserves existing version strings
```

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
| `~/.claude/CLAUDE.md` | `omh install` | Rules block for `o-kb-mcp` tools + user preferences |
| `~/.claude/skills/<name>/SKILL.md` | `omh skills pull` | Skill content used by Claude Code |
| `~/.claude/agents/<name>.md` | `omh agents pull` | Agent definitions used by Claude Code |
| `~/.claude/workflows/<name>.ts` | `omh workflows pull` | Workflow pipelines used by Claude Code |
| `assets/manifest.json` | `make manifest` | Versioned asset registry with dependency graph |

`~/.claude/CLAUDE.md` is managed with idempotent marker comments — repeated installs or updates replace only the managed sections, leaving any user content outside those markers untouched.

---

## How to extend

### Contributing a new skill

1. Create a directory `assets/skills/<name>/` with a `SKILL.md` file.
2. The frontmatter must contain at least `version: 1.0.0` and `name: <name>`.
3. Run `make manifest` — the script auto-computes sha256 and registers the new skill.
4. Open a pull request.

### Contributing a new agent

1. Create `assets/agents/<name>.md`.
2. The frontmatter must contain `version: 1.0.0`, `name: <name>`, and a `skills:` list declaring which skills this agent needs.
3. Run `make manifest` — the script reads the frontmatter and populates `dependencies.skills` automatically.
4. Validate the dep graph: every skill name in `skills:` must exist in `assets/skills/`.

### Contributing a new workflow

1. Create `assets/workflows/<name>.ts`.
2. Use `agentType: '<agent-name>'` string literals when invoking agents. The build script extracts these automatically.
3. Run `make manifest` — the script populates `dependencies.agents` via regex extraction.
4. Validate: every agent name must exist in `assets/agents/`.

---

## Roadmap

- **PyPI release** — `pip install oh-my-harness` / `uvx omh install`.
- **`omh` commands as MCP tools** — Claude Code can invoke `omh skills update` or `omh kb use` via natural language without leaving the chat.
- **Additional harness support** — VS Code Copilot, Cursor, and other assistants that support a skills/agents directory convention.
- **Agent-to-agent dependencies** — extend the dependency graph so agents can declare other agents as dependencies (e.g. `context` agent always pulled alongside `developer`).

---

## Why oh-my-harness

Most AI tools promise intelligence. oh-my-harness delivers **continuity**.

Your AI assistant today forgets everything when the session ends. It doesn't know that your team writes tests before implementation, that your API uses snake_case, that the `developer` agent should always run the `implement` skill before anything else. You either re-explain this every time or accept a generic, mediocre collaborator.

oh-my-harness makes your assistant **truly yours**:

- **Context that accumulates** — every decision you make, every pattern you establish, every architecture you document goes into the knowledge base. Next session, next project, next team member — it's all there.
- **Skills that compose** — pull the `developer` agent and its six skill dependencies land automatically: implementation methodology, testing strategy, environment management, code review practice, research technique, and AI/ML engineering. One command, zero setup friction.
- **Workflows that encode your process** — the `create-feature` workflow isn't just a prompt; it's a full multi-agent pipeline that writes the user story, implements the feature, runs QA and SRE validation in parallel, loops up to three times on failures, and opens a PR. Your process, encoded once, executed consistently.
- **Provider agnostic** — oh-my-harness sits above the model layer. Switch from Claude Code to Cursor tomorrow and your knowledge base, skills, and agents come with you.

The harness is only as powerful as the knowledge you put into it. oh-my-harness gives you the structure to make that investment pay off from day one — and compound over time.

---

## License

Apache License 2.0. See [LICENSE](LICENSE).
