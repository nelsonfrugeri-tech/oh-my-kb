---
version: 1.0.0
---

<!-- content_version: 1.0.0 | locale: pt-BR | updated: 2026-06-06 -->
# Scribe — playbook para escrever notas no oh-my-harness

Esta skill diz ao harness **como preencher os campos** que o `kb_write` espera.
O contrato mecânico (quais campos são obrigatórios, os valores válidos de `type`,
o modelo `Note`) é validado pelo código — esta skill trata apenas de **julgamento**:
quando escrever, qual tipo escolher, como escrever um summary que facilite o recall,
quais entidades extrair e como descobrir notas existentes para criar links.

Leia isto **antes** de cada chamada a `kb_write` até que as regras sejam automatizadas
pelo `o-kb-agents`. O corpo de toda nota deve seguir [`skill://scribe/template.md`](skill://scribe/template.md).

---

## 1. Criar uma nota nova vs. atualizar uma existente (`supersedes`)

Uma nota é **conhecimento imutável num ponto no tempo**. Não edite uma nota
existente; em vez disso, escreva uma nota nova e defina o campo `supersedes`
com o id da nota que está sendo substituída.

| Situação | O que fazer |
|---|---|
| Registrar algo novo (uma decisão que acabamos de tomar, um evento que acabou de acontecer, um procedimento que acabou de ser definido) | **Criar** — chamar `kb_write` com `supersedes = null`. |
| O usuário pede explicitamente para **revisar**, **atualizar**, **corrigir** ou **substituir** uma nota existente | **Superseder** — chamar `kb_search` para encontrar o id da nota anterior, depois `kb_write` com `supersedes = <id-anterior>`. A nota nova traz o conteúdo atualizado; a antiga permanece arquivada no histórico. |
| O usuário está fazendo uma pergunta ou explorando — nenhum conhecimento novo está sendo registrado | **Não escreva.** `kb_write` é para *registrar* conhecimento, não para conversar. |

Sinais do usuário que significam "superseder": "atualiza", "corrige", "revisa",
"agora ficou assim", "muda para", "a partir de hoje X em vez de Y".

Se não tiver certeza entre "isso corrige uma nota existente" e "isso é algo novo",
pergunte ao usuário uma vez. Não adivinhe.

## 2. Escolhendo o `type`

O enum é fechado: `decision | event | procedure | reference | conversation`.
Escolha a natureza **dominante**; não misture.

- **decision** — uma escolha feita entre alternativas, com uma justificativa. A
  palavra-chave é "decidimos X porque Y". Se não houver Y, provavelmente é
  `reference`.
- **event** — algo que aconteceu, com data. Incidentes, releases, lançamentos,
  reuniões. "Em 2026-05-30 o pipeline de embedding ficou fora do ar."
- **procedure** — passo a passo de "como fazer X". Reproduzível. Se um leitor
  futuro vai executar estes passos, é um procedimento.
- **reference** — um fato, uma definição, uma restrição permanente. Conhecimento
  de fundo estável. "O vetor denso do bge-m3 tem 1024 dimensões."
- **conversation** — uma troca notável cujo resultado é o significado. Use com
  parcimônia; se a conversa produziu uma decisão, escreva a decisão.

**Natureza mista?** Escolha o tipo sobre o qual a nota é *principalmente*. Se uma
decisão foi tomada durante um incidente, são duas notas: um `event` para o
incidente, um `decision` para o que foi decidido.

## 3. Escrevendo o `summary` — aqui o recall é ganho ou perdido

O `summary` é o texto que será embutido para busca por similaridade. Ele
**não** é um rótulo. É uma **prosa densa, específica e auto-contida** — um único
parágrafo (~200–800 chars) que outro agente poderia ler isoladamente e
entender do que a nota trata e por que é relevante.

**Regras**:

1. Não repita o título. O summary deve dizer algo que o título não diz.
2. Não escreva rótulos formulaicos ("Esta nota é sobre X"). Escreva o conteúdo.
3. Seja específico: nomeie o sistema, a decisão, a restrição, os atores.
   Prosa genérica recupera genericamente.
4. Seja auto-contido: o leitor não deve precisar abrir o arquivo para saber
   o que a nota cobre.
5. Não use listas com marcadores. Bullets não embute bem. Use prosa.

**Exemplos** — a diferença entre ruim e bom é o recall:

> ❌ "Decision about authentication." *(rótulo genérico, inútil para recall)*

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

Um summary mais curto que ~200 chars quase sempre significa "rótulo, não conteúdo".
Um summary mais longo que ~800 chars quase sempre significa "você colocou conteúdo
do corpo no summary". O corpo tem seu próprio campo.

## 4. Extraindo `entities`

`entities` é uma lista de substantivos de domínio sobre os quais a nota *trata*.
Eles são exibidos junto à nota, mas não fazem parte do contrato de embedding —
são metadados opcionais para filtragem e agrupamento visual.

- Incluir: nomes de sistemas, nomes de produtos/serviços, nomes de times ou
  pessoas se forem relevantes, tecnologias específicas, conceitos formais.
- Excluir: palavras genéricas ("sistema", "código", "usuário"), artigos, qualquer
  coisa que você pudesse substituir por um sinônimo sem mudar o significado.

| Título / summary | Boas entidades | Por quê |
|---|---|---|
| "Decisão de migrar do Postgres 14 para 16 no banco de pedidos" | `["postgres", "pedidos-db", "migração"]` | Sistemas específicos + a operação. |
| "Procedimento de rotação de chave KMS no api-gateway" | `["kms", "api-gateway", "rotação-de-chave"]` | Concreto, pesquisável. |
| "Reunião sobre roadmap" | `[]` ou pule a nota | Genérico demais — provavelmente não deveria ser uma nota. |

De duas a seis entidades é a forma certa. Dez é ruído.

## 5. Propondo `links_out`

Antes de escrever, **chame `kb_search`** com o tema da nova nota. Se notas
relevantes existentes aparecerem, inclua seus ids em `links_out`. Isso transforma
o corpus de um conjunto de notas em um grafo navegável.

Heurísticas para o que linkar:

- A nota que esta **sucede, contradiz ou refina**. Geralmente combinado com
  `supersedes` para substituições diretas; `links_out` para "ver também".
- Os **eventos** que motivaram uma decisão, ou as **decisões** causadas por
  um evento.
- O **procedimento** referenciado por uma decisão (para que o próximo leitor
  possa agir).
- Outras **referências** que definem os termos usados por esta nota.

Não linke por similaridade de palavras — linke por relação semântica real. Um
link que o leitor não poderia prever a partir do contexto é um link errado.

### Quanto linkar (limites quantitativos)

*Estes são limites de julgamento — `kb_write` não os enforça. O servidor
aceita notas com qualquer número de `links_out` e não valida scores. A
responsabilidade de aplicar estes critérios é sua.*

**Limite máximo: no máximo 5 links por nota.**
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
- `_PREFETCH_MULTIPLIER` em `oh_my_harness/kb/services/search.py` (padrão atual: 4)
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
   `oh_my_harness/kb/services/search.py`, toda a distribuição de scores muda — recalibre.

**BGE-M3:** os vetores denso e esparso do BGE-M3 são treinados com objetivos
complementares (semântica vs. lexical). A concordância entre as duas listas
tende a ser menor do que com modelos unimodais — os scores RRF médios ficam
no intervalo 0.018–0.028 em buscas típicas, raramente chegando ao máximo
teórico. Leve isso em conta ao interpretar histogramas de scores.

## 6. Regras mecânicas (validadas pelo código, listadas apenas para consciência)

Estas são validadas pelo modelo `Note` e pelo handler do `kb_write`. Você
**não precisa memorizá-las** porque o servidor rejeitará violações com uma
mensagem clara — mas conhecê-las evita idas e vindas desnecessárias:

- `title`, `project`, `summary` não podem ser vazios ou conter apenas espaços.
- O comprimento do `summary` deve estar dentro de `[SUMMARY_MIN_LEN, SUMMARY_MAX_LEN]`
  (atualmente 200–800 chars).
- `summary` não pode ser igual ao `title` (após remover espaços em branco).
- `type` deve ser um dos cinco valores do enum.
- `links_out` e `supersedes` devem ser UUIDs válidos.
- `universe` é **definido pelo servidor** e não faz parte da entrada da ferramenta — nunca o inclua. O servidor resolve o universo ativo na inicialização a partir de `KB_UNIVERSE`; o schema de entrada rejeita campos extras. Consulte [ADR-002](../../../../docs/adr/ADR-002-server-bound-universe.md).

Todo o restante — a *qualidade* do summary, a *escolha certa* do tipo,
as *entidades não triviais* — é responsabilidade sua.

## 7. O corpo segue o template

O campo `body` é markdown longo. Ele deve seguir a estrutura em
[`skill://scribe/template.md`](skill://scribe/template.md), que adapta as
seções por `type` da nota. O template garante **consistência visual**; a
skill garante **julgamento de conteúdo**. Os dois são complementares.
