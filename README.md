# oh-my-harness

> Plataforma local de knowledge base (RAG híbrido + grafo de notas) exposta via MCP, para uso com Claude Code e outros harnesses compatíveis.

---

## O que é

`oh-my-harness` provê uma base de conhecimento pessoal indexada no Qdrant (busca densa + esparsa via BGE-M3) e exposta como servidor MCP. Notas são arquivos markdown no disco, versionáveis no git. O Claude (ou qualquer harness MCP) acessa via tools:

- `kb_write` — registrar nota com embedding automático
- `kb_search` — busca híbrida (RRF fusion)
- `kb_tree` / `kb_expand` — navegação por grafo
- `kb_recent` — recall temporal

---

## Pré-requisitos

| Ferramenta | Para quê |
|------------|----------|
| Python 3.12+ | Pacote |
| [uv](https://docs.astral.sh/uv/) | Gerenciador de dependências |
| Docker (rodando) | Container do Qdrant |
| `make` | Atalhos de workflow |

> PyPI: ainda não. Use o clone local descrito abaixo.

---

## Instalação local — passo a passo

```bash
# 1. Clone
git clone https://github.com/nelsonfrugeri-tech/oh-my-kb.git
cd oh-my-kb

# 2. Instala dependências (cria .venv via uv sync)
make install

# 3. Rode o wizard de setup
uv run omh install
```

O wizard `omh install` é interativo. Ele faz 5 perguntas e depois pede confirmação antes de aplicar.

### O que o wizard pergunta

| # | Pergunta | Padrão |
|---|----------|--------|
| 1 | Diretório de notas | `~/oh-my-harness` |
| 2 | Nome do knowledge base (universe) | `default` |
| 3 | Porta local do Qdrant | `6333` |
| 4 | Cache dos modelos | `~/.cache/oh-my-harness/models` |
| 5 | Harness (`claude-code`, etc.) | `claude-code` |

Aperte **Enter** em qualquer pergunta para aceitar o padrão. Tudo padrão funciona.

### O que ele faz após você confirmar

- Sobe container Docker `oh-my-harness-qdrant` na porta escolhida
- Cria o diretório de notas e a primeira knowledge base (universe `default`)
- Escreve `~/.config/oh-my-harness/config.toml`
- Insere o bloco de regras de uso do kb no início do seu `~/.claude/CLAUDE.md` (para o Claude Code saber usar as tools)
- Baixa o modelo BGE-M3 no primeiro uso (~2 GB, demora alguns minutos)

### Verifique que está tudo no ar

```bash
uv run omh status         # Qdrant + universe + config
uv run omh kb list        # deve mostrar "default *"
```

Pronto. Abra o Claude Code em qualquer projeto e peça algo como:

> "Use kb_write para registrar: escolhemos Qdrant como vector store."

O Claude vai chamar `kb_write` via MCP, a nota vai pro disco em `~/oh-my-harness/default/` e o embedding pro Qdrant.

---

## CLI — `omh`

Estado atual (PR de redo da CLI em andamento):

| Comando | O que faz |
|---------|-----------|
| `omh install` | Wizard interativo. Idempotente. |
| `omh start` / `stop` / `status` | Ciclo de vida do container Qdrant |
| `omh reindex [--universe NAME]` | Reconciliar Qdrant com arquivos em disco |
| `omh kb create <name>` | Criar knowledge base nova (universe) |
| `omh kb list` | Listar knowledge bases (`*` = ativo) |
| `omh kb use <name>` | Trocar knowledge base ativa |
| `omh resource list` | Listar resources MCP (skill scribe etc.) |
| `omh resource pull [--all]` | Baixar resource(s) para `~/.claude/` |
| `omh resource diff [<id>]` | Diff local vs servidor |
| `omh resource update [<id>]` | Aplicar atualizações |

---

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `OMH_CONFIG_DIR` | `~/.config/oh-my-harness` | Onde fica o `config.toml` |
| `KB_NOTES_ROOT` | `~/oh-my-harness/<kb>` | Override do diretório de notas |
| `KB_QDRANT_URL` | `http://localhost:6333` | URL do Qdrant |
| `KB_UNIVERSE` | (kb ativa no config) | Override da kb ativa no MCP |

---

## Roadmap próximo

- **`omh skills` / `omh agents`** (top-level) — substituem `omh resource`. Vão buscar `.md` versionados em `assets/` deste repo via `raw.githubusercontent.com`, com `pull / diff / update` e contrato SemVer por arquivo.
- **CLAUDE.md gerado pelo `omh install`** vai injetar `repo_url` e `manifest_url` para o Claude saber checar versões novas sem perguntar.
- **Cada comando `omh` exposto como tool MCP** — Claude Code (ou outro harness) consegue invocar `omh_skills_pull`, `omh_agents_diff`, etc. por linguagem natural. Mesmo verbo no terminal e no chat.
- **PyPI** — distribuição via `uv tool install oh-my-harness` quando a CLI estiver estabilizada.

---

## Desenvolvimento

```bash
make check      # lint + typecheck + tests (CI gate)
make lint       # ruff check
make typecheck  # mypy oh_my_harness
make test       # pytest
make format     # ruff format
```

Notas e código vivem em:

```
oh_my_harness/
├── kb/                    # o-kb-mcp (knowledge base)
│   ├── agents/            # bootstrap + injeção de regras no CLAUDE.md
│   ├── cli/               # `omh` CLI (install wizard, kb, resource, reindex)
│   ├── core/              # Note, slug, serialização
│   ├── embedding/         # BGE-M3 embedder
│   ├── infra/             # QdrantContainer (Docker SDK)
│   ├── mcp/               # MCP server + tools (kb_*) + skill scribe
│   ├── services/          # Indexer, SearchService, NavigationService
│   └── storage/           # QdrantStore (hybrid search com RRF)
assets/                    # skills + agents distribuídos via raw.githubusercontent
└── manifest.json
tests/
docs/adr/
```

---

## Licença

Consulte o arquivo [LICENSE](LICENSE).
