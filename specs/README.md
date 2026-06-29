# Domain Design System — AI Observability Platform

Spec-driven, versionado, separado por **domínio de negócio** e **agente executor**.

> Toda regra é escrita uma vez, em um único lugar. Cada agente lê apenas as regras do seu escopo.

## Estrutura

```
specs/
├── README.md                       ← este arquivo
├── 00-glossary.md                  vocabulário canônico (40+ termos)
├── 01-naming-conventions.md        padrões de naming (código + dados + API)
├── 02-event-schema.md              contrato de evento (append-only log)
├── schemas/                        JSON Schemas compartilhados
│   ├── event.v1.json               envelope
│   ├── event-types.v1.json         sub-shapes por type (discriminator)
│   ├── attributes.v1.json          whitelist de keys em attributes
│   ├── span.v1.json                OTLP genai.*
│   ├── run.v1.json
│   └── judge-result.v1.json
├── domains/                        regras por domínio (15)
│   ├── 03-tracing.md
│   ├── 04-agent-orchestration.md
│   ├── 05-replay.md
│   ├── 06-cost.md
│   ├── 07-judge.md
│   ├── 08-storage.md
│   ├── 09-api.md
│   ├── 10-ui.md
│   ├── 11-auth.md
│   ├── 12-infra.md
│   ├── 13-sandbox.md               replay isolation (Firecracker)
│   ├── 14-data-governance.md       PII, retention, LGPD/GDPR
│   └── 15-conformance.md           contract tests, CI lint, versionamento
└── agents/                         contrato por agente executor
    ├── ingest-agent.md
    ├── graph-tracer-agent.md
    ├── replay-agent.md
    ├── judge-agent.md
    ├── query-agent.md
    ├── ui-agent.md
    └── platform-agent.md
```

## Regra de ouro

> **Um agente nunca lê o PRD inteiro. Ele lê o seu card (`agents/<agent>.md`) e, a partir dele, navega para os domínios que ele tem permissão de tocar.**

Card de agente declara:

1. **Domínios lidos** — quais `domains/*.md` ele pode consultar
2. **Domínios proibidos** — o que ele **não** pode decidir sozinho
3. **Contratos de entrada/saída** — schemas que ele consome/produz
4. **Invariantes** — regras que **nunca** pode violar
5. **Telemetria esperada** — o que ele deve emitir sobre si mesmo

## Versão

- Spec versionada por arquivo: `<file>.md` ganha `.vN` quando contrato muda de forma incompatível
- Mudanças compatíveis (adição de campo opcional) **não** quebram versão
- Toda mudança quebra-glasso precisa de ADR em `decisions/`
- Regras de versionamento + coexistência + sunset → `15-conformance.md`

## Princípios

| # | Princípio | Consequência prática |
|---|---|---|
| P1 | **Event sourcing é a verdade** | Toda observação vira `event`; UI e métricas derivam |
| P2 | **Append-only por padrão** | `events` e `checkpoints` nunca dão UPDATE no payload |
| P3 | **Reproduzibilidade é first-class** | Toda mutação carrega `seed` ou referência determinística |
| P4 | **Custo é telemetria, não afterthought** | Toda chamada externa emite `cost_usd` no mesmo span |
| P5 | **Determinismo de replay > fidelidade** | Replay perfeito onde dá, aproximado onde não dá — nunca opaco |
| P6 | **Schema > convenção** | Código lê JSON Schema, não valida por duck typing |
| P7 | **Erro é dado** | Toda falha vira `event.type = error` com `error.code` tipado |
| P8 | **Spec é executada** | Conformance tests + CI lint garantem `spec == código` |

## Mapa rápido: "onde está a regra de X?"

| Pergunta | Arquivo |
|---|---|
| Como nomeio um span? | `01-naming-conventions.md` |
| Qual o shape de um evento (envelope)? | `02-event-schema.md` + `schemas/event.v1.json` |
| Qual o shape de `payload` por `type`? | `schemas/event-types.v1.json` |
| Quais keys são válidas em `attributes`? | `schemas/attributes.v1.json` |
| Como funciona handoff multi-agent? | `domains/04-agent-orchestration.md` |
| Como calculo `cost_usd`? | `domains/06-cost.md` |
| Quem decide sampling? | `domains/03-tracing.md` § Sampling |
| Quais SLOs? | `domains/12-infra.md` § SLOs + PRD §6 |
| Como isolar replay? | `domains/13-sandbox.md` |
| Como tratar PII? | `domains/14-data-governance.md` |
| Como garantir conformidade? | `domains/15-conformance.md` |
| Quem implementa cada peça? | `agents/<agent>.md` |
| O que significa X? | `00-glossary.md` |
