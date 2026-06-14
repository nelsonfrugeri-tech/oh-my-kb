---
version: 1.0.0
name: drink-context
description: |
  Carrega o contexto do projeto atual: notas recentes da knowledge base (últimos
  5 dias filtrado por projeto) + context.md do projeto quando o volume na KB é
  baixo. Também atualiza context.md sob solicitação de mudança grande.
  Triggers: /drink_context, drink context, carregar contexto, contexto do projeto,
  recall contexto.
type: command
---

# drink-context — Carregador de Contexto do Projeto

Ao ser invocado, este skill instrui o harness a spawnar o agent `context`
(subagent_type: `context`) e seguir integralmente as instruções dele.

O agent `context` resolve o projeto atual, consulta a KB e entrega um bloco
de contexto estruturado para a sessão. Nenhuma ação adicional é necessária aqui.
