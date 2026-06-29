# Agent Card — `query-agent`

**Responsabilidade:** Query API REST/Read-only. Lista runs, retorna trace, executa compare.

## Domínios lidos

| Domínio | Lê? |
|---|---|
| `00-glossary.md` | ✅ |
| `01-naming-conventions.md` | ✅ |
| `02-event-schema.md` | ✅ (valida responses) |
| `03-tracing.md` | ✅ (entende OTLP genai.* para montar trace tree) |
| `04-agent-orchestration.md` | ✅ (entende handoffs para `/trace`) |
| `05-replay.md` | ✅ (apenas expõe `GET /v1/runs/{id}/replay`; **não** é o engine) |
| `06-cost.md` | ✅ (agregações cost por agent/tool/prompt_version) |
| `07-judge.md` | ✅ (expõe `GET /v1/runs/{id}/judge`) |
| `08-storage.md` | ✅ (Postgres, ClickHouse, pgvector) |
| `09-api.md` | ✅ (autoridade — implementa) |
| `11-auth.md` | ✅ (JWT, scopes, RLS) |
| `14-data-governance.md` | ✅ (respeita `gdpr.erased`, lineage, export) |
| `15-conformance.md` | ✅ (contract tests) |

## Domínios proibidos

- `10-ui.md` — não renderiza
- `12-infra.md` — não decide deploy (lê config)
- `13-sandbox.md` — não inicia sandbox (delega p/ replay-agent)

## Contratos de entrada

| Input | Validação |
|---|---|
| Path params | UUID v7 regex |
| Query string | Pydantic v2 + JSON Schema |
| Headers | `Authorization` (JWT), `X-Org-Id` (validado contra token) |
| Body (POST) | Pydantic v2 + JSON Schema |

## Contratos de saída

| Output | Schema |
|---|---|
| Run | `schemas/run.v1.json` |
| Trace tree | OTLP-compatible `{spans: [Span], edges: [(parent, child)]}` |
| Events list | `Event[]` (paginada) |
| Comparison | `Comparison` (Pydantic v2) |
| Judge results | `JudgeResult[]` |
| Errors | formato canônico (PRD `09-api.md` §Erros) |

## Invariantes

1. **Read-only** — NUNCA muta estado.
2. **Latência `/trace` p95 < 300ms** — para run com até 500 spans.
3. **Paginação cursor-based** — nunca offset.
4. **Org isolation rigorosa** — RLS + validação de `org_id` no controller.
5. **Cache headers** — `ETag` para `/runs/{id}` (imutável após `run.end`).
6. **OpenAPI canônico** — `/openapi.json` é fonte para SDK TS.
7. **Versionamento por path** — `/v1/...`; breaking → `/v2/...`.
8. **Rate limit por user** — 60 req/min (Redis).
9. **Tracing self** — toda request emite span `query-agent.handle_request`.

## Endpoints (delegação)

```
GET    /v1/runs                    → list, paginated
GET    /v1/runs/{id}               → single run
GET    /v1/runs/{id}/trace         → tree
GET    /v1/runs/{id}/events        → events list
GET    /v1/runs/{id}/checkpoints   → checkpoints list
GET    /v1/runs/{id}/replay        → { url, session_id } (delega p/ replay-agent)
GET    /v1/runs/{id}/similar       → similar runs (pgvector)
POST   /v1/runs/{id}/judge         → enqueue (delega p/ judge-agent)
GET    /v1/runs/{id}/judge         → list results
POST   /v1/compare                 → comparison (delega p/ judge-agent)
POST   /v1/score                   → alias p/ /judge
```

## Telemetria do próprio agent

| Métrica | Tipo | Labels |
|---|---|---|
| `query_requests_total` | counter | `endpoint`, `status` |
| `query_latency_seconds` | histogram | `endpoint` |
| `query_cache_hit_total` | counter | `endpoint` |
| `query_p95_per_endpoint` | gauge (rec) | `endpoint` |

## Onde mora

```
services/query-api/
├── app/
│   ├── main.py
│   ├── routers/
│   │   ├── runs.py
│   │   ├── trace.py
│   │   ├── compare.py
│   │   └── admin.py
│   ├── auth.py
│   ├── pagination.py
│   ├── cache.py
│   └── tracing.py
├── tests/
└── Dockerfile
```

## Dependências externas

- Postgres (RLS habilitado)
- ClickHouse (agregações)
- Redis (rate limit + cache)
- S3 (signed URLs)
- replay-agent e judge-agent (HTTP client)

## Out of scope

- Escrever eventos (delegado ao `ingest-agent`)
- Rodar replay ou judge (delegado)
- Renderizar UI (delegado)
