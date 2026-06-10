# oh-my-harness

> Plataforma de tuning e personalização de harness para agentes de IA. Expõe um knowledge base via MCP (`o-kb-mcp`) e um servidor de agentes em construção (`o-agents-mcp`).

---

## O que é oh-my-harness?

oh-my-harness é uma plataforma com dois MCPs:

- **`o-kb-mcp`** — knowledge base pessoal exposta via MCP. Notas ficam em markdown no disco e são indexadas no Qdrant com busca híbrida (densa + esparsa via bge-m3), navegação por grafo (`links_out`) e recall temporal (`created_at`).
- **`o-agents-mcp`** — servidor de agentes (em construção, issue #58). Stub funcional instalável; implementação completa vira em breve.

Funciona com qualquer harness compatível com MCP: Claude Code, Claude Desktop, Cursor, ou qualquer cliente MCP.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                   AI Harness (ex: Claude Code)       │
│              ~/.claude/CLAUDE.md  (regras injetadas) │
└──────────────┬──────────────────────────┬───────────┘
               │ MCP                       │ MCP
       ┌───────▼────────┐        ┌────────▼────────┐
       │   o-kb-mcp     │        │  o-agents-mcp   │
       │  (knowledge    │        │  (em construção │
       │   base tools)  │        │   issue #58)    │
       └───────┬────────┘        └─────────────────┘
               │
       ┌───────▼────────┐
       │    Qdrant       │  hybrid search (BGE-M3)
       │  (local Docker) │  dense + sparse vectors
       └───────┬────────┘
               │
       ┌───────▼────────┐
       │  ~/oh-my-      │  plain markdown files
       │  harness/      │  git-versionável
       └────────────────┘
```

---

## Pré-requisitos

| Ferramenta | Para quê |
|------------|----------|
| Python 3.12+ | Requerido pelo pacote |
| [uv](https://docs.astral.sh/uv/) | Gerenciamento de dependências |
| Docker | Roda o Qdrant local |
| `make` | Encapsula os workflows comuns |

---

## Quick start

```bash
uv tool install oh-my-harness   # instala omh, o-kb-mcp, o-agents-mcp
omh install                      # wizard: configura Qdrant, bge-m3, universo default
```

Após o `omh install`, abra o Claude Code em qualquer projeto — o bloco de regras já está em `~/.claude/CLAUDE.md`.

Escreva a primeira nota:

```
Use kb_write to record: we chose Qdrant as our vector store.
```

---

## Desenvolvimento local (clone)

```bash
git clone https://github.com/nelsonfrugeri-tech/oh-my-kb.git
cd oh-my-kb
make install           # uv sync — cria .venv
docker compose up -d   # inicia Qdrant em localhost:6333
omh install            # provisiona o universo default
```

---

## Ferramentas MCP — o-kb-mcp

| Ferramenta | O que faz |
|------------|-----------|
| `kb_write` | Cria ou supersede uma nota markdown com embedding automático |
| `kb_search` | Busca híbrida (densa + esparsa) com RRF fusion |
| `kb_tree` | Visão em árvore do grafo de conhecimento |
| `kb_expand` | Lê uma nota completa com links resolvidos |
| `kb_recent` | Notas mais recentes por universo ou projeto |

---

## Busca híbrida

Cada nota gera dois vetores via bge-m3 em uma única passagem:
- **Vetor denso** (1024 dims) — semântica
- **Vetor esparso** (SPLADE) — léxico / BM25-like

O Qdrant combina os dois rankings com **Reciprocal Rank Fusion (RRF)** antes de retornar os resultados. O score RRF retornado por `kb_search` não é uma similaridade de cosseno normalizada; consulte a skill `scribe` para calibração de thresholds.

---

## Universos

Universos são namespaces isolados de conhecimento (ex: `work`, `personal`, `oss`):

```bash
omh kb create work              # cria um novo universo
omh kb list                     # lista todos (* = ativo)
omh kb use work                 # troca o universo ativo
```

Cada universo tem um diretório próprio (`~/oh-my-harness/<universo>/`) e uma coleção Qdrant independente.

A variável `KB_UNIVERSE` sobrescreve o universo ativo no servidor MCP; `KB_NOTES_ROOT` sobrescreve o diretório de notas.

---

## Reindexação

Se notas forem editadas diretamente no disco, reconcilie com o Qdrant:

```bash
omh reindex                    # reindexar o universo ativo
omh reindex --universe work    # reindexar um universo específico
```

`omh reindex` é **totalmente idempotente**.

---

## CLI — omh

```bash
omh [COMMAND]
```

| Comando | O que faz |
|---------|-----------|
| `omh install` | Wizard interativo: Qdrant, bge-m3, universo default. Idempotente. |
| `omh start` | Inicia o container Qdrant. |
| `omh stop` | Para o container Qdrant. |
| `omh status` | Exibe o estado atual do sistema. |
| `omh reindex [--universe NAME]` | Reconcilia Qdrant com os arquivos em disco. |
| `omh universe create <name>` | Cria universo: diretório + coleção Qdrant + entrada no config. |
| `omh universe list` | Lista universos configurados. |
| `omh universe use <name>` | Ativa um universo. |
| `omh resource list` | Lista os resources MCP disponíveis. |
| `omh resource pull [--all]` | Baixa resources MCP (ex: skill scribe). |

---

## Estrutura do projeto

```
oh_my_harness/
  __init__.py
  kb/                    # o-kb-mcp (knowledge base)
    agents/              # bootstrap, injeção de harness
    cli/                 # omh CLI (install, universe, resource, reindex)
    core/                # Note, slug, serialização
    embedding/           # BGE-M3 embedder
    infra/               # QdrantContainer (Docker SDK)
    mcp/                 # MCP server, tools, resources, skills
    services/            # Indexer, SearchService, NavigationService
    storage/             # QdrantStore
  agents/                # o-agents-mcp (em construção — issue #58)
    mcp/
      server.py          # placeholder main()
tests/
docs/
  adr/
```

---

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `OMH_CONFIG_DIR` | `~/.config/oh-my-harness` | Diretório do `config.toml` |
| `KB_NOTES_ROOT` | `~/oh-my-harness/<universo>` | Diretório de notas (override por universo) |
| `KB_QDRANT_URL` | `http://localhost:6333` | URL do servidor Qdrant |
| `KB_UNIVERSE` | (universo ativo no config) | Universo ativo no servidor MCP |

---

## Migração — oh-my-kb → oh-my-harness

Se você usava a versão anterior (`oh-my-kb`):

**Manifest:** o arquivo de manifest era `~/.claude/.omk-manifest.json`. Após instalar `oh-my-harness`, execute `omh resource pull --all` para gerar o novo manifest em `~/.claude/.omh-manifest.json`. O arquivo antigo pode ser removido manualmente.

**Container Docker:** o container se chamava `oh-my-kb-qdrant`. O novo nome é `oh-my-harness-qdrant`. Na próxima vez que rodar `omh install`, um novo container será criado. O antigo pode ser removido com:
```bash
docker stop oh-my-kb-qdrant && docker rm oh-my-kb-qdrant
```

**Variável de ambiente:** `OMK_CONFIG_DIR` foi renomeada para `OMH_CONFIG_DIR`.

**Comando CLI:** `omk` foi renomeado para `omh`. Usuários com `omk` instalado receberão um erro no próximo reinstall — isso é esperado em um rename major.

---

## Desenvolvimento

```bash
make check     # lint + typecheck + tests (CI gate)
make lint      # ruff check
make typecheck # mypy oh_my_harness
make test      # pytest
make format    # ruff format
```

---

## Licença

Consulte o arquivo [LICENSE](LICENSE).
