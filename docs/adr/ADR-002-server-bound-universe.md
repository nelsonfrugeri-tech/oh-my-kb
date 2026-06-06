# ADR-002: Server-bound universe in `o-kb-mcp`

## Status

Accepted — 2026-06-06 (implemented in PR #23, issue #21).

## Context and problem statement

`oh-my-kb` partitions knowledge into **universes**: top-level namespaces that
isolate Qdrant collections (`kb_<slug(universe)>`) and on-disk note roots
(`<KB_NOTES_ROOT>/<slug(universe)>/...`). Search never crosses universes,
and a note belongs to exactly one universe for its lifetime.

`o-kb-mcp` is a stdio MCP server consumed by an LLM harness (e.g. Claude
Code). Each harness invocation calls tools like `kb_write` and `kb_search`.

The architectural question is: **how does the active universe reach the
tool handler?** Two paths exist:

1. The server reads `KB_UNIVERSE` from its environment at boot and injects
   it into every handler call. The tool input does not carry a `universe`
   field.
2. The tool input carries `universe` as a (required or optional) field, and
   the model fills it on every call.

This decision is recurrent: it shows up in code review every time a new tool
is added. It was raised explicitly in the review of PR #23 as deserving an
ADR.

## Decision drivers

- **Isolation by default**: a cross-universe write is a corruption of the
  knowledge graph; rolling it back is manual and expensive.
- **Trust boundary**: the harness is a non-deterministic process (an LLM
  filling slots). Anything the model can put in the input, the model can
  also put wrong.
- **Operator control**: the operator who runs the MCP server has a known
  source of truth for the active universe (env vars, MCP client config).
  The model does not.
- **Symmetry**: `kb_write` and `kb_search` must agree on the universe.
  Splitting that scope between server and input creates an N×M matrix of
  "what if they disagree?" cases.
- **Cost of running multiple servers**: low — `o-kb-mcp` is a stdio process,
  the harness already supports multiple MCP servers per session, and the
  bge-m3 model cache is shared across processes via `~/.cache/huggingface`.

## Considered options

### Option A — Server-bound universe via `KB_UNIVERSE` (chosen)

The server reads `KB_UNIVERSE` (default `"default"`) at boot in
`oh_my_kb.mcp.config.get_active_universe()`. `build_context()` captures it
into an immutable `KBServerContext`, and every handler receives that
context. The tool input schema for `kb_write` and `kb_search` has
`additionalProperties: false` and no `universe` field.

- **Pros**
  - Cross-universe writes by a confused model are **impossible by
    construction** — the tool input cannot widen the universe.
  - One choke-point (`get_active_universe`) controls the binding; future
    changes (e.g. reading from `~/.config/oh-my-kb/config.toml`) are
    localized.
  - Symmetry between `kb_write` and `kb_search` is automatic — both pull
    from the same context.
  - The model has one less slot to fill, which means one fewer thing it
    can fill wrong.
- **Cons**
  - Switching universes requires restarting `o-kb-mcp` with a different
    env, or running multiple instances side-by-side.
  - Working on multiple universes from the same harness session requires
    multiple MCP-server entries in the harness configuration (one per
    universe).
  - Operators must understand that `KB_UNIVERSE` is set in the **MCP
    client config** (the JSON the harness reads), not by the model.

### Option B — `universe` as an optional input field, default = server-bound

The input schema gains an optional `universe` string. If absent, the server
falls back to `KB_UNIVERSE`. If present, it overrides per call.

- **Pros**
  - One harness session can address multiple universes without running
    multiple servers.
  - Backward-compatible with the chosen option (callers that omit
    `universe` behave identically).
- **Cons**
  - Opens the door to **accidental cross-universe writes** the moment the
    model decides to "be helpful" and fill the field with a guessed value.
    This is exactly the failure mode the isolation boundary is for.
  - Doubles the verification surface for every handler: "what if the
    input universe disagrees with the active one?" must be answered for
    every new tool.
  - Couples the tool schema to a concept (multi-universe addressing)
    that the harness can already achieve via multiple MCP servers.

### Option C — `universe` is required in the input, no server fallback

Every call must specify the universe. The server holds no implicit state.

- **Pros**
  - The server is stateless w.r.t. universes; one server can serve all of
    them.
  - The contract is explicit at every call site.
- **Cons**
  - Same accidental-cross-write risk as Option B, but worse: there is no
    default to fall back to, so every model error is a write error.
  - The harness has to learn what the active universe is from somewhere,
    which pushes the problem to the harness configuration anyway — and
    now there are two places to keep in sync instead of one.
  - Hostile to the harness: an extra slot every call has to fill correctly.

### Option D — Read the active universe from `omk`'s TOML config

The server reads `~/.config/oh-my-kb/config.toml` at boot to find the
currently active universe (whatever `omk universe use <name>` last set).
The input still carries no `universe` field.

- **Pros**
  - Single source of truth shared between CLI and MCP server.
  - No env var to plumb through the harness config.
- **Cons**
  - Introduces a hidden global between two adapters of the same domain,
    which complicates testing and reasoning ("which `omk` config does this
    server read?" when there are profiles).
  - The CLI↔MCP bridge is its own design problem (out of scope here —
    tracked as a future issue).
- **Status**: deferred. This is a forward-compatible extension of Option A:
  `get_active_universe()` can grow a TOML fallback later without breaking
  any caller.

## Decision

Chosen: **Option A — server-bound universe via `KB_UNIVERSE`**, with
Option D as the forward-compatible extension path.

Rationale: the dominant driver is **isolation by default**. The harness is
an LLM filling slots, and the failure mode of a cross-universe write
(notes leak between disjoint knowledge spaces; Qdrant collection picks up
strangers) is silent and hard to repair. The cost of the chosen option —
"to switch universes, restart the server with a different env" — is
operationally trivial because:

- MCP clients already support multiple named MCP servers, so multi-universe
  harnesses run one `o-kb-mcp` per universe.
- The bge-m3 model cache is shared on disk, so additional instances are
  cheap (one process per universe, one model cache).
- Universes change rarely; the dominant access pattern is one universe per
  workflow session.

Option D remains an open path: when the CLI↔MCP bridge issue lands,
`get_active_universe()` can read TOML transparently. Today's contract does
not need to change for that to happen.

## Consequences

### Positive

- The boundary is **strict by construction**. The JSONSchema
  (`additionalProperties: false`, no `universe` field) means a malformed
  attempt to inject `universe` is rejected by the SDK before any handler
  runs.
- One choke-point (`get_active_universe`) for any future change to how the
  universe is resolved.
- Symmetry between `kb_write` and `kb_search` is automatic — both read
  from the same `KBServerContext`.

### Negative

- Switching the active universe at runtime is not supported. Operators
  manage multi-universe setups by configuring multiple MCP servers in
  their harness (one entry per universe).
- The harness operator must understand that `KB_UNIVERSE` is set in the
  **MCP client config** (the JSON the harness reads), not by the model.
  README documents this; the tool descriptions repeat it for the model
  ("The universe is server-bound — do not include it in the input.").

### Risks and mitigations

- **Risk**: an operator misconfigures `KB_UNIVERSE` and the server writes
  into the wrong universe. **Mitigation**: the startup log prints the
  active universe to stderr (`_log_startup` in `server.py`); operators
  see the actual value at boot.
- **Risk**: a contributor adds a new MCP tool and forgets to pull universe
  from `KBServerContext`, accepting it from input instead. **Mitigation**:
  this ADR + the scribe SKILL note + the consistent pattern in the two
  existing tools. Future work: a fitness function (architecture test) that
  fails CI if any tool's `inputSchema` contains a `universe` property.

## Related decisions and references

- Issue #21 — `feat(mcp): servidor o-kb-mcp com kb_search e kb_write` — the implementation issue.
- PR #23 — the implementation; review comment requesting this ADR.
- `oh_my_kb/mcp/config.py` — `KB_UNIVERSE`, `get_active_universe()`.
- `oh_my_kb/mcp/server.py` — `KBServerContext`, `build_context()`.
- `oh_my_kb/mcp/tools/kb_write.py` — tool description carries the rule for the model; `inputSchema` enforces it for the protocol.
- `oh_my_kb/mcp/tools/kb_search.py` — same shape, symmetrically.
- `oh_my_kb/mcp/skills/scribe/SKILL.md` §6 — mechanical rules section; mentions the constraint alongside other enforced contracts.

## Notes

- Date: 2026-06-06
- Author: Nelson Frugeri
- Reviewers: (to be filled at PR time)
