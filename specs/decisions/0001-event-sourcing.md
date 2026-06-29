# 0001 — Event sourcing como modelo canônico

- **Status:** accepted
- **Date:** 2026-06-29
- **Deciders:** @bruno
- **Consulted:** —
- **Informed:** @team

## Contexto e problema

O produto precisa ser fonte de verdade para auditoria de runs de agentes LLM. Logs tradicionais não capturam causalidade. Precisamos de modelo que permita replay, attribution de custo e diff semântico.

## Forças em jogo

- Auditabilidade (LGPD, debugging, regressões)
- Custo de storage cresce com volume
- Query API precisa ser rápida p/ run de até 500 spans
- Replay bit-a-bit é diferencial competitivo (PRD §13)

## Opções consideradas

### Opção 1 — Logs estruturados + métricas

- **Prós:** simples, tooling maduro
- **Contras:** sem causalidade explícita, replay impossível

### Opção 2 — Event sourcing canônico (escolhida)

- **Prós:** causalidade, replay, audit trail imutável
- **Contras:** curva de aprendizado, exige disciplina de append-only

### Opção 3 — OpenTelemetry puro + state derivado

- **Prós:** padrão aberto
- **Contras:** OTel não tem semântica `genai.*` estável, e replay exige event log de qualquer jeito

## Decisão

Opção 2: tabela `events` append-only é fonte de verdade. UI, métricas e replay derivam dela. ClickHouse é mirror analítico.

## Consequências

### Positivas

- Replay determinístico possível (PRD UC5)
- Diff semântico de runs trivial (diff no log)
- Auditoria LGPD-friendly (append-only)

### Negativas

- Storage cresce linearmente com volume
- Mutation de schema é caro (imutability)

### Neutras

- Sampling head-based no SDK (10% success, 100% error)

## Trade-offs explícitos

| O que ganhamos | O que perdemos |
|---|---|
| Replay bit-a-bit | Custo de storage ~2x maior que logs |
| Auditoria nativa | Flexibilidade de "corrigir" evento ruim |

## Validação

- Replay do run `r_demo` reproduz output em 100% das tools
- Storage de 1 run ≤ 50 KB metadata
- Query `/trace` p95 < 300ms

## Notas

- Relação: `02-event-schema.md`, `05-replay.md`
- Próxima revisão: semana 4 (após load test)
