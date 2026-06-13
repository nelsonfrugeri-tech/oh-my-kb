<!-- content_version: 1.0.0 | locale: pt-BR | updated: 2026-06-06 -->
# Template do corpo da nota

Este arquivo define a **estrutura do campo `body`** de toda nota
escrita no oh-my-harness. Ele **não** define o `summary` — esse é
escrito separadamente, conforme as regras em
[`skill://scribe/SKILL.md`](skill://scribe/SKILL.md).

O corpo é markdown simples. Seções marcadas **(obrigatório)** devem estar presentes;
seções marcadas **(opcional)** podem ser omitidas quando não se aplicam.

---

## Seções comuns (toda nota tem estas)

### Contexto (obrigatório)

Um parágrafo curto: *por que esta nota existe?* Qual situação, pergunta ou
gatilho levou ao registro? Seja conciso — algumas frases. Se o
contexto for longo, provavelmente é uma nota separada (e deve ser linkada via
`links_out`).

### Referências (opcional)

URLs citadas, nomes de documentos relacionados ou apontadores em texto livre. **Links
internos entre notas vão em `links_out` (o campo estruturado), não aqui.**

---

## Seções específicas por tipo

Escolha o bloco que corresponde ao `type`. Não misture.

### `decision`

#### Decisão (obrigatório)

Enuncie a decisão em uma ou duas frases, no presente. "Adotamos X." Se um
parágrafo não for suficiente para enunciar a decisão, provavelmente você está
tentando registrar múltiplas decisões — separe-as.

#### Alternativas consideradas (obrigatório)

Uma lista curta das alternativas avaliadas. Para cada uma, uma linha sobre o que era
e por que não foi escolhida. O objetivo é tornar a *troca* visível
para o próximo leitor.

#### Consequências (obrigatório)

O que esta decisão implica agora: o que faremos, o que não faremos, o que
precisaremos revisitar, quem é responsável pelo acompanhamento. De dois a cinco tópicos.

### `event`

#### O que aconteceu (obrigatório)

Narrativa factual e datada. Quando, onde, o que, quem estava envolvido. Passado.
Sem interpretação nesta seção — mantenha neutro.

#### Impacto (obrigatório)

O que quebrou, o que ficou lento, o que foi perdido, o que foi aprendido. Se o evento
foi positivo (um lançamento, um marco), o que mudou por causa dele.

#### Causa raiz (opcional)

Se a causa raiz for conhecida. Não especule — se não tiver certeza, omita e linke à
nota de investigação em `links_out`.

#### Próximos passos (opcional)

Acompanhamentos concretos (com responsável se aplicável).

### `procedure`

#### Quando usar (obrigatório)

A pré-condição para executar este procedimento. "Use quando o release do api-gateway
tem menos de 30 minutos e a latência p99 está acima de 500ms."
Sem esta seção, leitores futuros executarão o procedimento na situação errada.

#### Passos (obrigatório)

Numerados, executáveis, prontos para copiar e colar. Cada passo é um verbo no
imperativo. Inclua comandos, caminhos de arquivo, saídas esperadas.

#### Validação (obrigatório)

Como confirmar que o procedimento funcionou. A métrica, o dashboard, o
comando cuja saída prova o sucesso.

#### Reversão (opcional, quando aplicável)

Como desfazer, ou apontador (em `links_out`) para o procedimento inverso.

### `reference`

#### Conteúdo (obrigatório)

O fato, a definição, a restrição. Seja preciso — referências são citadas por outras
notas. Se a referência puder mudar com o tempo (um número de versão, um
valor de configuração), inclua a data em que foi observada.

#### Aplicabilidade (opcional)

Onde esta referência se aplica e onde não se aplica. Referências sem
escopo tendem a ser mal aplicadas.

### `conversation`

#### Resumo do diálogo (obrigatório)

Sobre o que foi a conversa e quem participou. Passado.

#### Decisões / próximos passos (obrigatório)

O que a conversa produziu. **Se houver decisões concretas, escreva
notas `decision` separadas para cada uma e linke a esta conversa via
`links_out`.** A nota de conversa é o *rastro*; as notas de decisão são
o *resultado*.

---

## Regras rígidas

1. **Não coloque o summary no corpo.** O summary tem seu próprio campo e
   passa pelo embedding; o corpo é para o leitor que já decidiu que
   a nota é relevante.
2. **Não cole transcrições brutas** a menos que a transcrição em si seja o
   conhecimento (ex.: uma entrevista de postmortem). Caso contrário, resuma.
3. **Mantenha a formatação mínima.** Cabeçalhos markdown conforme as seções acima,
   blocos de código para comandos, parágrafos normais para o restante. Sem HTML, sem
   badges personalizadas, sem emojis decorativos.
4. **Date tudo que pode mudar.** Versões, custos, latências, valores de política
   — inclua a data em que foram escritos para que um leitor futuro saiba
   se a informação ainda é atual.
