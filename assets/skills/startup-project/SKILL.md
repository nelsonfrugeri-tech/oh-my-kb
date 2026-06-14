---
version: 1.0.0
name: startup-project
description: |
  Inicializa um novo projeto dentro do oh-my-harness — pergunta link remoto e nome,
  então invoca o agent explorer para gerar a pasta do projeto na KB ativa e o
  context.md inicial. Use quando o usuário entrar pela primeira vez em um projeto
  ou quando ele pedir explicitamente "/startup_project" / "inicializar projeto" /
  "configurar projeto na kb".
  Triggers: /startup_project, inicializar projeto no oh-my-harness, startup project.
type: command
---

# Startup Project — Skill de Inicialização

## Propósito

Esta skill registra o slash command `/startup_project` e define como o harness deve
inicializar um projeto no oh-my-harness.

Quando ativada, o harness spawna o agent `startup_project` e segue as instruções dele.
O agent é o responsável pela orquestração completa — esta skill apenas aciona o processo.

## Ativação

Esta skill é ativada por qualquer um dos seguintes triggers:

- Slash command explícito: `/startup_project`
- Linguagem natural: "inicializar projeto no oh-my-harness"
- Linguagem natural: "configurar projeto na kb"
- Linguagem natural: "startup project"
- Primeiro uso em um projeto sem `context.md` na KB ativa

## Instrução ao Harness

Quando esta skill for ativada:

1. Spawne o agent `startup_project` (subagent_type: `startup_project`)
2. Passe qualquer contexto disponível na sessão atual (cwd, nome de projeto mencionado,
   URL de repositório mencionada) como contexto inicial no prompt do agent
3. Aguarde o retorno do agent e apresente o resultado ao usuário
4. Não execute as etapas do workflow diretamente no loop principal — o agent é o
   orquestrador; respeite a divisão de responsabilidades

## O que o Agent `startup_project` Faz

O agent `startup_project` conduz o seguinte fluxo:

1. Coleta link remoto do repositório (opcional) e nome do projeto
2. Resolve a KB ativa via `~/.config/oh-my-harness/config.toml`
3. Invoca o agent `explorer` para gerar o `context.md` inicial
4. Reporta ao usuário o caminho criado, sinais detectados e próximos passos

Para o comportamento detalhado, consulte `assets/agents/startup_project.md`.

## Resultado Esperado

Ao final da execução, o usuário recebe:

- Caminho do `context.md` criado na KB ativa
- Sinais principais do projeto (linguagem, framework, tipo)
- Instrução de próximo passo: `/drink_context` para carregar o contexto na sessão

## Dependências

- Agent `explorer` (PR1) — responsável por gerar o `context.md`
- Agent `startup_project` — orquestrador desta skill
- KB ativa configurada em `~/.config/oh-my-harness/config.toml` (fallback: `knowledge_base`)
