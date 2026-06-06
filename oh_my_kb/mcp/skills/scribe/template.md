# Note body template

This file defines the **structure of the `body` field** of every note
written into oh-my-kb. It does **not** define the `summary` — that is
prose written separately, per the rules in
[`skill://scribe/SKILL.md`](skill://scribe/SKILL.md).

The body is plain markdown. Sections marked **(required)** must be present;
sections marked **(optional)** may be omitted when they don't apply.

---

## Common sections (every note has these)

### Contexto (required)

One short paragraph: *why does this note exist?* What situation, question or
trigger led to recording this? Keep it tight — a few sentences. If the
context is long, it's probably a separate note (and should be linked via
`links_out`).

### References (optional)

Quoted URLs, related document names, or freeform pointers. **Internal links
between notes go in `links_out` (the structured field), not here.**

---

## Type-specific sections

Pick the block that matches `type`. Don't mix.

### `decision`

#### Decisão (required)

State the decision in one or two sentences, in the present tense. "We
adopt X." If a paragraph isn't enough to state the decision, you're
probably trying to record multiple decisions — split.

#### Alternativas consideradas (required)

A short list of the alternatives you weighed. For each, one line on what it
was and why it wasn't picked. The point is to make the *trade-off* visible
to the next reader.

#### Consequências (required)

What this decision now implies: what we'll do, what we won't do, what
we'll need to revisit, who owns the follow-up. Two to five bullets.

### `event`

#### O que aconteceu (required)

Factual, dated narrative. When, where, what, who was involved. Past
tense. No interpretation in this section — keep it neutral.

#### Impacto (required)

What broke, what slowed, what was lost, what was learned. If the event
was a positive one (a launch, a milestone), what changed because of it.

#### Causa raiz (optional)

If the root cause is known. Don't speculate — if unsure, omit and link to
the investigation note in `links_out`.

#### Próximos passos (optional)

Concrete follow-ups (with owner if applicable).

### `procedure`

#### Quando usar (required)

The precondition for running this procedure. "Use when the api-gateway
release is less than 30 minutes old and p99 latency is over 500ms."
Without this section, future readers will run the procedure in the wrong
situation.

#### Passos (required)

Numbered, executable, copy-pasteable. Each step is a verb in the
imperative. Include commands, file paths, expected outputs.

#### Validação (required)

How you confirm the procedure worked. The metric, the dashboard, the
command whose output proves success.

#### Reversão (optional, when applicable)

How to undo, or pointer (in `links_out`) to the inverse procedure.

### `reference`

#### Conteúdo (required)

The fact, the definition, the constraint. Be precise — references get
quoted by other notes. If the reference can drift (a version number, a
configuration value), include the date you observed it.

#### Aplicabilidade (optional)

Where this reference applies and where it doesn't. References without
scope tend to be misapplied.

### `conversation`

#### Resumo do diálogo (required)

What the conversation was about and who was in it. Past tense.

#### Decisões / próximos passos (required)

What the conversation produced. **If there are concrete decisions, write
separate `decision` notes for each and link to this conversation via
`links_out`.** A conversation note is the *trace*; the decision notes are
the *outcome*.

---

## Hard rules

1. **Don't put the summary in the body.** The summary is its own field and
   goes through embedding; the body is for the reader who already decided
   the note is relevant.
2. **Don't paste raw transcripts** unless the transcript itself is the
   knowledge (e.g. a postmortem interview). Otherwise, summarise.
3. **Keep formatting minimal.** Markdown headers per the sections above,
   code blocks for commands, normal paragraphs otherwise. No HTML, no
   custom badges, no decorative emoji.
4. **Date everything that can drift.** Versions, costs, latencies, policy
   values — include the date you wrote them so a later reader knows
   whether the information is still current.
