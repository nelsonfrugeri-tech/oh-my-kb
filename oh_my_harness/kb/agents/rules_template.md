# kb-mcp — memory and knowledge base rules

kb-mcp is this project's long-term memory. Notes persist as Markdown files
indexed in Qdrant. The active universe is **{universe}**. Every query and write
is scoped to it automatically — never pass the universe as a tool argument.

Tools: `kb_search` (semantic retrieval), `kb_tree` (structural directory),
`kb_expand` (full note + resolved links), `kb_write` (register/supersede a note),
`kb_recent` (temporal recall by creation date).

---

## When to search — `kb_search`

Use when the user refers to past context, an established decision, convention,
or procedure, and the information is not already in the current session.
Also prefer `kb_search` when the universe is large or the question is about
content similarity ("what do we know about X?", "what's our policy on Y?").

Do not use `kb_search` to explore structure — that is `kb_tree`.

---

## When to navigate — `kb_tree` + `kb_expand`

Use `kb_tree` when the question is structural: "what exists?", "what topics
does this universe cover?", "what notes are in project X?". It returns a
project-grouped map of note ids, titles, types, and summaries — no embedding
cost, no full body.

Use `kb_expand` to read a note in full and resolve its outbound links. Follow
the knowledge graph hop by hop by calling `kb_expand` again on any returned
link id. Chain calls for multi-hop exploration:

```
kb_tree → pick id → kb_expand → follow link id → kb_expand → ...
```

Prefer navigation over search when the universe or project is small, or when
the question is about relationships between notes.

---

## When to recall — `kb_recent`

Use when the question is **temporal**: "what happened recently in project X?",
"what changed in the last week?", "what are the latest decisions?".
`kb_recent` returns notes ordered by creation date (newest first), optionally
filtered by project, topic, or time window (`since: "7d"`, `"30d"`, ISO date).

Do not use `kb_recent` as a substitute for semantic search — it orders by time,
not relevance. Use it when recency is the primary criterion.

---

## When to write — `kb_write`

Write **only** when the user explicitly asks to register, record, annotate, or
save something. Do not write as a side-effect of answering a question.

Before every `kb_write` call, read the scribe skill installed at
`~/.claude/skills/scribe/SKILL.md` (and `template.md` in the same directory).

To **update** an existing note: find it with `kb_search`, then call `kb_write`
with `supersedes` set to the old note's UUID. The old note is preserved as
history; the new note carries the updated content.

Before writing, run `kb_search` on the note's topic with `top_k=10` (not the
default 5) and include relevant existing note UUIDs in `links_out` — a larger
candidate pool lets the score filter and qualitative criteria work correctly.

---

## Decision guide

```
User refers to past context or an established convention?
  └─ not in session → kb_search

User asks what exists or what relates?
  └─ kb_tree for the map → kb_expand to open a note → repeat to follow links

User asks about recent events, latest decisions, or what changed?
  └─ kb_recent (add since="7d" / "30d" to narrow the window)

User explicitly asks to record / register / save something?
  └─ kb_write (set supersedes if updating an existing note)

None of the above → answer from session context; no kb call needed
```

---

## Skills & agents disponíveis localmente

Skills instalados em `~/.claude/skills/<nome>/SKILL.md` e agents em
`~/.claude/agents/<nome>.md`. Para consultar versões disponíveis no repositório
oficial, use o manifest:

- Repositório: {repo_url}
- Manifest: {manifest_url}

Se o usuário pedir "verifica se tem versão nova de X", consulte o manifest acima
e compare a `version` do skill/agent com a versão local (no frontmatter YAML do `.md`).
