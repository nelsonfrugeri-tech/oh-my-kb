<!-- content_version: 1 | locale: pt-BR | updated: 2026-06-13 -->
# oh-my-harness — regras de memória e base de conhecimento

oh-my-harness é um harness modular para IA. A knowledge base ativa é **{kb_name}**.

Módulos:
- **kb** — knowledge base persistente via MCP (ferramentas abaixo). As notas são
  escopadas à knowledge base ativa automaticamente — nunca passe como argumento de ferramenta.
- **agents** — agentes pessoais via MCP (veja seção "Agentes pessoais" abaixo).

A CLI `omh` orquestra tudo: `omh kb`, `omh skills`, `omh agents`.

Ferramentas: `kb_search` (recuperação semântica), `kb_tree` (diretório estrutural),
`kb_expand` (nota completa + links resolvidos), `kb_write` (registrar/superseder uma nota),
`kb_recent` (recall temporal por data de criação).

---

## Quando buscar — `kb_search`

Use quando o usuário se referir a contexto passado, uma decisão estabelecida, convenção
ou procedimento, e a informação não estiver na sessão atual.
Prefira também `kb_search` quando a knowledge base for grande ou a pergunta for sobre
similaridade de conteúdo ("o que sabemos sobre X?", "qual é nossa política sobre Y?").

Não use `kb_search` para explorar estrutura — para isso existe `kb_tree`.

---

## Quando navegar — `kb_tree` + `kb_expand`

Use `kb_tree` quando a pergunta for estrutural: "o que existe?", "quais tópicos
esta knowledge base cobre?", "quais notas estão no projeto X?". Ele retorna um mapa
agrupado por projeto com ids, títulos, tipos e summaries das notas — sem custo de
embedding, sem o corpo completo.

Use `kb_expand` para ler uma nota completa e resolver seus links de saída. Siga
o grafo de conhecimento salto a salto chamando `kb_expand` novamente em qualquer
id de link retornado. Encadeie chamadas para exploração multi-salto:

```
kb_tree → escolha o id → kb_expand → siga o id do link → kb_expand → ...
```

Prefira navegação em vez de busca quando a knowledge base ou projeto for pequeno, ou quando
a pergunta for sobre relações entre notas.

---

## Quando usar recall temporal — `kb_recent`

Use quando a pergunta for **temporal**: "o que aconteceu recentemente no projeto X?",
"o que mudou na última semana?", "quais são as últimas decisões?".
`kb_recent` retorna notas ordenadas por data de criação (mais recentes primeiro), com filtro
opcional por projeto, tópico ou janela de tempo (`since: "7d"`, `"30d"`, data ISO).

Não use `kb_recent` como substituto para busca semântica — ele ordena por tempo,
não por relevância. Use quando a recência for o critério principal.

---

## Quando escrever — `kb_write`

Escreva **apenas** quando o usuário pedir explicitamente para registrar, anotar ou
salvar algo. Não escreva como efeito colateral de responder uma pergunta.

Antes de cada chamada a `kb_write`, leia o skill scribe instalado em
`~/.claude/skills/scribe/SKILL.md` (e `template.md` no mesmo diretório).

Para **atualizar** uma nota existente: encontre-a com `kb_search`, depois chame `kb_write`
com `supersedes` definido para o UUID da nota antiga. A nota antiga é preservada como
histórico; a nova nota traz o conteúdo atualizado.

Antes de escrever, execute `kb_search` sobre o tema da nota com `top_k=10` (não o
padrão 5) e inclua os UUIDs de notas relevantes em `links_out` — um pool maior de
candidatos permite que o filtro de score e os critérios qualitativos funcionem corretamente.

---

## Guia de decisão

```
O usuário se refere a contexto passado ou a uma convenção estabelecida?
  └─ não está na sessão → kb_search

O usuário pergunta o que existe ou o que se relaciona?
  └─ kb_tree para o mapa → kb_expand para abrir uma nota → repita para seguir links

O usuário pergunta sobre eventos recentes, últimas decisões ou o que mudou?
  └─ kb_recent (adicione since="7d" / "30d" para restringir a janela)

O usuário pede explicitamente para registrar / salvar algo?
  └─ kb_write (defina supersedes se estiver atualizando uma nota existente)

Nenhum dos casos acima → responda a partir do contexto da sessão; nenhuma chamada kb é necessária
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
