---
version: 1.0.0
name: feature
description: |
  Cria uma feature ponta-a-ponta. Conduz o refinamento técnico interativo
  com architect ou ai-engineer, salva tudo no KB do oh-my-harness, e então
  dispara o workflow create-feature que cuida do resto (user_history → dev →
  loop[qa+sre] → PR).
  Use quando o usuário quer iniciar uma feature nova passando pelas fases:
  refinement_tech (interativo) → user_history → development → validation → PR.
  Triggers: /feature, criar feature, nova feature, começar feature.
type: workflow
---

# Feature — End-to-End Feature Creation

Você é o orquestrador da criação de uma feature nova. Conduza o usuário pelas fases
abaixo. Não pule etapas. Não invente nomes, decisões técnicas ou repositórios — pergunte.

## Setup inicial

1. **Nome da feature** — se o usuário não passou junto com `/feature`, pergunte qual é o nome.
   Gere também um `featureSlug` em kebab-case (snake_case se preferido) para diretórios e
   branches. Confirme o slug com o usuário antes de continuar.

2. **Track de implementação** — pergunte se é `developer` (default) ou `ai-engineer`.
   Sugira `ai-engineer` quando a descrição inicial mencionar LLM, RAG, embeddings, agente,
   prompt, modelo, NLP, classificação, recomendação. Caso contrário sugira `developer`.

3. **Repositório alvo** — pergunte qual repositório `owner/name` no GitHub vai receber o PR
   no final. Se o usuário não souber agora, registre como `null` e siga (o tech_pm e o
   implementer tentarão descobrir via `git remote` no momento de criar issue/PR).

## Fase 1 — `refinement_tech` (interativa)

Esta fase é a conversa de design com o especialista. Use o agente `architect` por padrão,
ou `ai-engineer` se o track for `ai-engineer` E o foco for arquitetura de IA. Você pode
invocar os dois em momentos diferentes se a feature tiver componentes mistos.

**Loop de refinamento:**

1. Faça **uma rodada** de perguntas ao especialista (use a tool `Agent` com `subagent_type`
   apropriado): peça uma análise inicial + 3-5 perguntas críticas para o usuário.
2. Apresente as perguntas ao usuário via `AskUserQuestion` (uma por vez se forem densas, ou
   agrupadas se forem rápidas).
3. Anote as respostas. Acumule no buffer de refinamento.
4. Pergunte ao usuário: "Quer aprofundar mais algum ponto, mudar de agente, ou já podemos
   consolidar o refinamento_tech?"
5. Se quer aprofundar: volte ao passo 1 com o contexto acumulado.
6. Se já está bom: prossiga para a consolidação.

**Consolidação:**

Peça ao agente atual (architect ou ai-engineer) para escrever o `refinement_tech.md` final
estruturado em seções:

```
# Refinement Tech — <nome da feature>

## Contexto e problema
## Objetivos técnicos
## Decisões de arquitetura
## Componentes e responsabilidades
## Trade-offs avaliados
## Riscos técnicos e mitigações
## Componentes de IA (se aplicável)
## Perguntas em aberto

---

## Histórico de discussão
<dump cronológico das perguntas e respostas do refinamento, em pt-BR>
```

**Salvar no KB:** chame `kb_write` (via ToolSearch para carregar o schema se preciso)
com path `<featureSlug>/refinement_tech.md` e o conteúdo consolidado. Confirme ao
usuário que foi salvo.

## Fase 2-5 — Disparar o Workflow

Depois do refinement_tech salvo, invoque o workflow `create-feature` com os args:

```
Workflow({
  name: "create-feature",
  args: {
    featureName: "<nome legível>",
    featureSlug: "<slug>",
    refinementContent: "<conteúdo completo do refinement_tech.md>",
    track: "developer" | "ai-engineer",
    repo: "<owner/name ou null>",
  },
})
```

O workflow cuida de:
- `user_history` — tech_pm escreve user story, abre issue no GitHub, grava em `<slug>/user_history/user_history.md`
- `development` — implementer (developer ou ai-engineer) cria branch `feature/<slug>` e implementa
- `validation_loop` — qa (funcional + e2e) e sre (infra + load + stress) em paralelo, gravam evidências em `<slug>/validation/*.md`, loop até pass ou max 3 iterações
- `open_pr` — implementer abre PR usando template padronizado, OU escala para o usuário se 3 iterações falharem

## Quando o workflow retornar

Reporte o status ao usuário com clareza:

- `success` → mostre o link do PR e dos arquivos de evidência
- `blocked_at_development` ou `blocked_at_fix` → mostre o `blockedReason` e pergunte como o
  usuário quer destravar
- `failed_max_iterations` → mostre o histórico das 3 iterações (qa+sre issues por iteração)
  e pergunte se o usuário quer assumir manualmente

## Regras

- **Nunca** salve refinement_tech sem confirmar conteúdo com o usuário (ou ao menos um
  resumo dele).
- **Nunca** abra issue ou PR sem ter o refinement_tech salvo no KB primeiro.
- **Sempre** use AskUserQuestion para escolhas (track, repo, "podemos consolidar?"); nunca
  decida sozinho.
- **Em pt-BR** durante toda a interação com o usuário; os artefatos técnicos (markdown,
  schemas, código) seguem o que for natural ao contexto.
- Se o usuário interromper em qualquer ponto, salve o estado atual no KB (mesmo parcial)
  antes de parar — para retomar depois.
