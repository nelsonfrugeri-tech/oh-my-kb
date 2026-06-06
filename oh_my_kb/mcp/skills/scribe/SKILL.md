# Scribe — playbook for writing notes into oh-my-kb

This skill tells the harness **how to fill the slots** that `kb_write` expects.
The mechanical contract (which fields are required, valid `type` values, the
`Note` model) is enforced by code — this skill is only about **judgement**:
when to write, what type to pick, how to write a summary that recalls well,
which entities to extract, and how to discover existing notes to link to.

Read this **before** every `kb_write` call until the rules are automated by
`o-kb-agents`. The body of every note must follow [`skill://scribe/template.md`](skill://scribe/template.md).

---

## 1. Create a new note vs. update an existing one (`supersedes`)

A note is **immutable knowledge at a point in time**. Don't edit a note in
place; instead, write a new note and set its `supersedes` field to the id of
the one being replaced.

| Situation | What to do |
|---|---|
| Recording something new (a decision we just made, an event that just happened, a procedure that was just defined) | **Create** — call `kb_write` with `supersedes = null`. |
| The user explicitly asks to **revise**, **update**, **correct** or **replace** an existing note | **Supersede** — call `kb_search` to find the previous note's id, then `kb_write` with `supersedes = <previous-id>`. The new note carries the new content; the old one stays archived for history. |
| The user is asking a question or exploring — no new knowledge is being recorded | **Don't write.** `kb_write` is for *registering* knowledge, not for chatting. |

Signals from the user that mean "supersede": "atualiza", "corrige", "revisa",
"agora ficou assim", "muda para", "a partir de hoje X em vez de Y".

If unsure between "this corrects an existing note" and "this is brand new",
ask the user once. Don't guess.

## 2. Choosing the `type`

The enum is closed: `decision | event | procedure | reference | conversation`.
Pick the **dominant** nature; don't mix.

- **decision** — a choice made between alternatives, with a rationale. The
  defining word is "we decided X because Y". If there's no Y, it's probably
  `reference`.
- **event** — something that happened, dated. Incidents, releases, launches,
  meetings. "On 2026-05-30 the embedding pipeline went down."
- **procedure** — step-by-step "how to do X". Reproducible. If a future
  reader will run these steps, it's a procedure.
- **reference** — a fact, a definition, a standing constraint. Stable
  background knowledge. "The bge-m3 dense vector is 1024-dim."
- **conversation** — a notable exchange whose outcome is the meaning. Use
  sparingly; if the conversation produced a decision, write the decision
  instead.

**Mixed nature?** Pick the type that the note is *primarily about*. If a
decision was made during an incident, that's two notes: one `event` for the
incident, one `decision` for what we decided.

## 3. Writing the `summary` — this is where recall is won or lost

The `summary` is the text that gets embedded for similarity search. It is
**not** a label. It is **dense, specific, self-contained prose** — a single
paragraph (~200–800 chars) that another agent could read in isolation and
understand what the note is about and why it matters.

**Rules**:

1. Don't repeat the title. The summary must say something the title doesn't.
2. Don't write formulaic labels ("This note is about X"). Write the content.
3. Be specific: name the system, the decision, the constraint, the actors.
   Generic prose retrieves generically.
4. Be self-contained: the reader shouldn't need to open the file to know
   what the note covers.
5. Don't bullet-list. Bullets don't embed well. Use prose.

**Examples** — the difference between bad and good is recall:

> ❌ "Decision about authentication." *(generic label, useless for recall)*

> ✅ "Decisão de adotar OIDC com PKCE como fluxo de autenticação do
> dashboard interno, em vez de OAuth2 client-credentials, porque o
> dashboard é consumido por usuários humanos e queremos token de sessão
> curto com refresh, não credenciais de serviço de longa duração."

---

> ❌ "Incident in the deploy pipeline."

> ✅ "No dia 2026-05-30 o pipeline de deploy do api-gateway ficou parado
> 47 minutos depois que a action `cache@v3` foi deprecada e quebrou a
> restauração do cache de dependências; mitigamos pinando `cache@v4`.
> Causa raiz: não escutávamos o feed de deprecation do GitHub."

---

> ❌ "How to roll back."

> ✅ "Procedimento para reverter um release de produção do api-gateway
> usando `kubectl rollout undo` no deployment `api-gateway-prod` no
> namespace `prod`, com janela de validação de 5 minutos no dashboard
> de latência p99 antes de declarar o rollback concluído. Use apenas
> quando o release atual está ativo há menos de 30 minutos; rollbacks
> mais antigos exigem o procedimento de migração de schema reverso."

A summary shorter than ~200 chars almost always means "label, not content".
A summary longer than ~800 chars almost always means "you put body content
into the summary". The body has its own field.

## 4. Extracting `entities`

`entities` is a list of domain nouns the note is *about*. They get displayed
alongside the note but are not part of the embedding contract — they're
optional metadata for filtering and visual grouping.

- Include: system names, product/service names, team or person names if
  they're load-bearing, specific technologies, formal concepts.
- Exclude: generic words ("system", "code", "user"), articles, anything you
  could replace with a synonym without changing meaning.

| Title / summary | Good entities | Why |
|---|---|---|
| "Decisão de migrar do Postgres 14 para 16 no banco de pedidos" | `["postgres", "pedidos-db", "migração"]` | Specific systems + the operation. |
| "Procedimento de rotação de chave KMS no api-gateway" | `["kms", "api-gateway", "rotação-de-chave"]` | Concrete, searchable. |
| "Reunião sobre roadmap" | `[]` or skip the note | Too generic — probably shouldn't be a note at all. |

Two to six entities is the right shape. Ten is noise.

## 5. Proposing `links_out`

Before writing, **call `kb_search`** with the topic of the new note. If
relevant existing notes come back, include their ids in `links_out`. This
turns the corpus from a bag of notes into a navigable graph.

Heuristics for what to link:

- The note this one **succeeds, contradicts, or refines**. Usually paired
  with `supersedes` for direct replacements; `links_out` for "see also".
- The **events** that motivated a decision, or the **decisions** caused by
  an event.
- The **procedure** referenced by a decision (so the next reader can act).
- Other **references** that define the terms this note uses.

Don't link by similarity of words — link by actual semantic relationship. A
link the reader couldn't predict from context is a wrong link.

### Quanto linkar (quantitative caps)

*Estes são limites de julgamento — `kb_write` não os enforça. O servidor
aceita notas com qualquer número de `links_out` e não valida scores. A
responsabilidade de aplicar estes critérios é sua.*

**Cap superior: máximo 5 links por nota.**
Acima de 5, a lista vira ruído de navegação — o leitor (humano ou agente)
perde a capacidade de distinguir o link central dos links periféricos.
Se `kb_search` devolver mais de 5 candidatos com relação genuína, escolha os
5 mais próximos semanticamente do tema da nota nova.

Ao buscar candidatos para `links_out`, use `top_k >= 10` — não o default de 5.
Com `top_k=5`, o filtro de score nunca elimina nada porque o harness já
recebe no máximo 5 candidatos. Um pool de 10 candidatos permite que o critério
qualitativo e o piso de score trabalhem como filtros reais.

**Piso de score: descarte hits com `score < 0.02`.**
O `score` devolvido por `kb_search` é uma pontuação RRF (Reciprocal Rank
Fusion) produzida pelo Qdrant, não uma similaridade de cosseno normalizada
entre 0 e 1. Com dois prefetch (vetor denso + vetor esparso) e o parâmetro
padrão `k = 60`, o score máximo teórico para um documento que apareça em
primeiro lugar nas duas listas é `2 / (60 + 1) ≈ 0.033`. Na prática:

| Faixa de score RRF | O que implica (com k=60, 2 listas) |
|--------------------|-------------------------------------|
| ≥ 0.025            | Rank ≤ 20 em ambas as listas, ou muito bem rankeado em uma (top-3 ou melhor) com presença razoável na outra |
| 0.015 – 0.025      | Presença moderada: top-50 em pelo menos uma lista, posição mais fraca na outra |
| < 0.015            | Hit fraco — ranking ≥ 73 em ambas as listas; coincidência superficial ou ruído |

*Derivação: `score = 1/(60+rank_a) + 1/(60+rank_b)`. Para score = 0.025 com ranks iguais: `2/(60+N) = 0.025 → N = 20`.*

O threshold de **0.02** é conservador: captura hits que aparecem
consistentemente nas duas listas sem incluir ruído.

> **Aviso — corpus pequeno:** em bases com ≤ 50 notas, o pior score
> possível já é `2/(60+50) ≈ 0.018`, e com ≤ 20 notas é `2/(60+20) = 0.025`
> — praticamente todos os resultados ficam acima de 0.02. Nesses casos o
> filtro de score não discrimina: confie inteiramente no critério qualitativo
> da seção anterior (relação semântica real, não similaridade de palavras).

Score ≥ 0.02 é condição necessária para considerar um candidato — mas não
é suficiente: um hit com score alto e sem relação semântica real com a nota
nova **não deve** ser linkado. O critério qualitativo da seção acima prevalece.

### Como calibrar

**Quando recalibrar:** mude estes números se algum destes parâmetros mudar:
- Modelo de embedding (substituir BGE-M3 por outro modelo)
- `k` do Qdrant RRF (padrão atual: 60)
- `_PREFETCH_MULTIPLIER` em `oh_my_kb/services/search.py` (padrão atual: 4)
- Tamanho típico do corpus (corpus > 500 notas pode tolerar threshold maior)

Os números acima derivam da fórmula RRF com `k = 60` (padrão do Qdrant) e
dois prefetches independentes. Para ajustá-los ao seu corpus:

1. **Observe a distribuição real.** Execute `kb_search` com 5–10 queries
   representativas do corpus e anote os scores dos hits. Olhe o histograma:
   onde há um vale natural entre hits relevantes e irrelevantes? Esse vale é
   o threshold ideal.

2. **Corpus muito especializado** (ex.: todas as notas falam do mesmo sistema)
   tem scores médios mais baixos porque a discriminação entre notas vizinhas é
   menor. Nesse caso considere baixar o threshold para 0.015.

3. **Corpus muito variado** (múltiplos projetos, domínios distintos) tem mais
   separação entre hits. Pode elevar o threshold para 0.025 sem perder recall
   relevante.

4. **Referência:** o algoritmo RRF é descrito em Cormack, Clarke & Buettcher
   (SIGIR 2009) e implementado nativamente pelo Qdrant Query API
   (`Fusion.RRF`). O `k = 60` original foi escolhido empiricamente pelos
   autores para suprimir outliers de ranking.

5. **Parâmetro interno `_PREFETCH_MULTIPLIER`:** o Qdrant pré-busca
   `top_k × 4` candidatos por sub-query antes de calcular o RRF. Com
   `top_k=10` (recomendado para links_out), o pool de candidatos por lista é
   40 documentos. Se `_PREFETCH_MULTIPLIER` mudar em
   `oh_my_kb/services/search.py`, toda a distribuição de scores muda — recalibre.

**BGE-M3:** os vetores denso e esparso do BGE-M3 são treinados com objetivos
complementares (semântica vs. lexical). A concordância entre as duas listas
tende a ser menor do que com modelos unimodais — os scores RRF médios ficam
no intervalo 0.018–0.028 em buscas típicas, raramente chegando ao máximo
teórico. Leve isso em conta ao interpretar histogramas de scores.

## 6. Mechanical rules (enforced by code, listed for awareness only)

These are validated by the `Note` model and the `kb_write` handler. You
**don't have to remember them** because the server will reject violations
with a clear message — but knowing them avoids round-trips:

- `title`, `project`, `summary` non-empty and non-whitespace.
- `summary` length must be within `[SUMMARY_MIN_LEN, SUMMARY_MAX_LEN]`
  (currently 200–800 chars).
- `summary` must not equal the `title` (after trimming whitespace).
- `type` must be one of the five enum values.
- `links_out` and `supersedes` must be valid UUIDs.

Everything else — the *quality* of the summary, the *right* choice of type,
the *non-trivial* entities — is your job.

## 7. The body follows the template

The `body` field is long-form markdown. It must follow the structure in
[`skill://scribe/template.md`](skill://scribe/template.md), which adapts the
sections per note `type`. The template enforces **visual consistency**; the
skill enforces **content judgement**. The two are complementary.
