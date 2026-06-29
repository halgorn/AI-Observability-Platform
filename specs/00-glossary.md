# 00 — Glossary

Vocabulário canônico. Toda spec, código e doc usa estes termos **exatamente** como definidos aqui.

> Conflito de termo = **bug de design**. Abrir ADR.

## Núcleo

| Termo | Definição | Não confundir com |
|---|---|---|
| **Run** | Uma execução completa de um agente, do input inicial ao output final. Identificada por `run_id` (UUID v7). | "trace" (Run é a unidade de negócio; trace é a representação visual) |
| **Step** | Uma transição discreta do state machine dentro de uma run. Indexada por `step` (int, monotonic). | "span" (Step é conceitual; span é a telemetria) |
| **Span** | Uma unidade de telemetria OTLP emitida por um nó/edge da run. Tem `parent_span_id`. | "event" (Span é a métrica; event é o fato) |
| **Event** | Linha append-only na tabela `events`. Fato imutável. | "log" (log é texto livre; event é estruturado e tipado) |
| **Checkpoint** | Snapshot serializado do state do LangGraph em um `step`. PK `(run_id, step)`. | "snapshot genérico" (checkpoint aqui é o `PostgresSaver` schema) |
| **Artifact** | Bloco versionado e imutável (prompt, código de agente, embedding). | "asset" (artifact tem `hash` + `version`) |
| **Handoff** | Transição explícita entre agentes em uma multi-agent run. | "tool call" (tool é chamada externa; handoff é delegação) |
| **Replay** | Re-execução determinística de uma run a partir de checkpoints. | "re-run" (re-run é não-determinístico; replay é bit-a-bit) |

## Domínio

| Termo | Defiinção |
|---|---|
| **Tracer** | Componente que emite spans/eventos (ex.: `GraphTracer`). |
| **Collector** | Serviço intermediário OTel que recebe OTLP e roteia. |
| **Ingest API** | Endpoint FastAPI que recebe OTLP e REST, persiste eventos. |
| **Judge** | Worker LLM-as-judge que atribui score a um span ou run. |
| **Run Compare** | Operação que diffa 2 runs semanticamente. |
| **Cost Attribution** | Rateio de `cost_usd` por `tool × step × agent`. |

## Identificadores

| Tipo | Formato | Geração |
|---|---|---|
| `run_id` | UUID v7 | client-side (sdk) ou server (api) |
| `span_id` | 16 bytes hex (OTLP) | OTel SDK |
| `trace_id` | 16 bytes hex (OTLP) | OTel SDK |
| `parent_span_id` | 16 bytes hex ou `null` | OTel SDK |
| `step` | int ≥ 0, monotonic por run | LangGraph runtime |
| `thread_id` | string, FK lógica p/ LangGraph | LangGraph runtime |
| `artifact_hash` | sha256 hex | builder |
| `judge_cache_key` | sha256(`model`, `input`, `output`) | judge worker |
| `seed` | int ou sha256 truncado | determinismo (replay, judge) |
| `session_id` (replay) | UUID v7 | server |

## Infra / plataforma

| Termo | Definição |
|---|---|
| **OTLP** | OpenTelemetry Protocol. gRPC ou HTTP. Transport canônico de spans. |
| **OTel** | OpenTelemetry. SDK + collector + semantic conventions. |
| **semconv** | Semantic conventions. Aqui: `genai.*` v0.4.x (PRD risco R-3). |
| **SLO** | Service Level Objective. Target mensurável (ex.: p95 < 300ms). |
| **SLI** | Service Level Indicator. A métrica que mede o SLO. |
| **SLA** | Service Level Agreement. Contrato (com cliente) baseado em SLOs. |
| **Burn rate** | Velocidade de consumo do error budget. Alerta típico: 2% em 1h, 5% em 6h. |
| **Error budget** | Orçamento de falha = `(1 - SLO) × janela`. Ex.: 99.5% × 30d = 3.6h de downtime. |
| **PII** | Personally Identifiable Information. Qualquer dado que identifica pessoa. |
| **PII redaction** | Substituição por placeholder mantendo shape (case, length). |
| **RLS** | Row-Level Security. Postgres feature para isolar dados por `org_id`. |
| **RBAC** | Role-Based Access Control. `owner > admin > member > viewer`. |
| **Tenant** | Sinônimo de **org** neste produto. |
| **Multi-tenant** | Vários orgs no mesmo deployment, isolados por RLS + JWT. |
| **IVFFlat** | Índice aproximado do `pgvector` para busca k-NN. v1 usa; v2 migra p/ Qdrant. |
| **Embedding** | Vetor denso de floats (dim 1536) que representa semântica de texto. |
| **Idempotency** | Operação que pode ser repetida sem efeito colateral. Garantida por `Idempotency-Key`. |
| **OTLP exporter** | Componente SDK que envia spans/metrics pra um endpoint OTLP. |
| **Token** | Unidade de LLM billing. `tokens_in` (prompt) + `tokens_out` (completion). |
| **Prompt** | Input textual ao LLM. Versionado em `artifacts` (semver). |
| **Completion** | Output do LLM. Também chamado de `output` ou `response`. |
| **Cost attribution** | Rateio de `cost_usd` por `agent × tool × step × prompt_version`. |
| **Feature flag** | Toggle on/off de comportamento. Default = conservador. |
| **Cold path / Hot path** | Hot = latência crítica (< 10ms). Cold = pode ser assíncrono. |
| **Canary** | Deploy com % pequeno de tráfego antes de promover. |
| **Blue-green** | Deploy com switch atômico entre dois ambientes. |
| **PITR** | Point-in-Time Recovery. Postgres feature p/ restore até um timestamp. |
| **RPO / RTO** | Recovery Point/Time Objective. Quanto dado/tempo aceito perder na恢复. |
| **ADR** | Architecture Decision Record. Documento imutável de decisão técnica. |
| **Runbook** | Passo-a-passo operacional de um cenário (incidente, deploy, etc.). |
| **Playbook** | Coleção de runbooks para um domínio. |
| **Postmortem** | Documento de análise de incidente, blameless. |
| **Service token** | API key scoped a um org, com permissões granulares (diferente de user JWT). |
| **Sandbox** | Ambiente isolado (Firecracker microVM) onde roda o replay. |

## Status e estados

| Status | Significado |
|---|---|
| `running` | Run em curso, sem evento terminal |
| `succeeded` | Step finalizou sem `error` |
| `failed` | Step finalizou com `error` |
| `timeout` | Excedeu `budget_ms` |
| `cancelled` | Cancelamento explícito (user ou upstream) |
| `replaying` | Run em modo replay (não conta em métricas de produção) |

## Tipos de evento (type)

Valores canônicos do campo `events.type`:

```
llm.call
tool.invoke
handoff
checkpoint
error
judge.result
run.start
run.end
step.start
step.end
artifact.link
```

> Sub-shapes de `payload` por `type` definidos em `schemas/event-types.v1.json`.
> Adicionar um novo tipo = **breaking change** no schema `event.v1`. Exige `event.v2`.

## Erros (error.code)

```
LLM_TIMEOUT
LLM_RATE_LIMIT
LLM_INVALID_OUTPUT
TOOL_TIMEOUT
TOOL_NOT_FOUND
TOOL_INVALID_ARGS
HANDOFF_REJECTED
CHECKPOINT_MISSING
REPLAY_DIVERGED
JUDGE_DISAGREEMENT
INGEST_REJECTED
SCHEMA_INVALID
AUTH_MISSING
AUTH_FORBIDDEN
AUTH_ROLE_INSUFFICIENT
AUTH_TOKEN_EXPIRED
AUTH_TOKEN_INVALID
BUDGET_EXCEEDED
PII_DETECTED
GDPR_ERASURE_PENDING
GDPR_ERASURE_FAILED
GDPR_EXPORT_FORBIDDEN
SANDBOX_BOOT_FAILED
SANDBOX_SECCOMP_VIOLATION
SANDBOX_NETWORK_VIOLATION
SANDBOX_TIMEOUT
SANDBOX_OOM
SPEC_VERSION_UNSUPPORTED
RATE_LIMITED
RUN_NOT_FOUND
RUN_ALREADY_TERMINAL
INTERNAL_ERROR
DEPENDENCY_DOWN
UNKNOWN
```

> Source-of-truth = `schemas/event.v1.json#/$defs/ErrorCode` + `schemas/attributes.v1.json`. Mantidos sincronizados pelo linter `specs/tools/check_enums.py`.
