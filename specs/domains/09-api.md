# 09 — API Domain

FastAPI + Pydantic v2. Async nativo, type-safety ponta-a-ponta.

## Stack

| Camada | Tool |
|---|---|
| Framework | FastAPI 0.115+ |
| Validação | Pydantic v2 |
| Auth | Clerk (JWT verification) |
| Server | Uvicorn (ASGI) |
| OpenAPI | auto-gerado, served em `/openapi.json` |
| Deploy | Fly.io (múltiplas regiões) |

## Endpoints canônicos

### Ingest

| Method | Path | Body | Auth | Resposta |
|---|---|---|---|---|
| POST | `/v1/traces` | OTLP HTTP | service token | 200 |
| gRPC | `/opentelemetry.proto.collector.trace.v1.TraceService/Export` | OTLP | service token | ack |
| POST | `/v1/events` | `Event[]` | service token | `{accepted: int, rejected: int}` |

### Query

| Method | Path | Auth | Resposta |
|---|---|---|---|
| GET | `/v1/runs` | user | `Run[]` paginado |
| GET | `/v1/runs/{id}` | user | `Run` |
| GET | `/v1/runs/{id}/trace` | user | árvore de spans |
| GET | `/v1/runs/{id}/events` | user | `Event[]` paginado |
| GET | `/v1/runs/{id}/checkpoints` | user | `Checkpoint[]` |
| GET | `/v1/runs/{id}/replay` | user | `{url, session_id}` |
| GET | `/v1/runs/{id}/similar` | user | `Run[]` (k=10) |
| POST | `/v1/runs/{id}/judge` | user | `{job_id}` |
| GET | `/v1/runs/{id}/judge` | user | `JudgeResult[]` |

### Compare

| Method | Path | Body | Resposta |
|---|---|---|---|
| POST | `/v1/compare` | `{run_a, run_b, dimension}` | `Comparison` |
| POST | `/v1/score` | `{run_id, dimensions[]}` | `{job_id}` |

### Admin

| Method | Path | Auth | Resposta |
|---|---|---|---|
| GET | `/v1/orgs/{id}/slo` | admin | `SLOStatus[]` |
| POST | `/v1/orgs/{id}/slo` | admin | `SLO` |
| GET | `/v1/healthz` | open | `{status: "ok"}` |
| GET | `/v1/readyz` | open | `{checks: {...}}` |

## Filtros e paginação (padrão)

```
GET /v1/runs?agent=planner&status=failed&since=24h&limit=50&cursor=...
```

- `since` aceita `15m`, `24h`, `7d`, ou ISO 8601.
- `limit` default 50, max 200.
- `cursor` opaco (base64 de `(started_at, run_id)`).
- Resposta: `{items: [...], next_cursor: "..."|null}`.

## Headers obrigatórios

```
Authorization: Bearer <clerk_jwt>
X-Org-Id: org_xxxxx         (resolvido do token, validado)
X-Run-Id: <uuid>             (echo, para tracing)
Idempotency-Key: <uuid>      (POST, dedupe em 24h)
```

## Erros — formato canônico

```json
{
  "error": {
    "code": "INGEST_REJECTED",
    "message": "payload.size exceeds 5MB",
    "request_id": "req_xxx",
    "details": {
      "field": "payload",
      "limit_bytes": 5242880
    }
  }
}
```

| HTTP | Códigos |
|---|---|
| 400 | `INGEST_REJECTED`, `SCHEMA_INVALID` |
| 401 | `AUTH_MISSING`, `AUTH_FORBIDDEN` |
| 404 | `RUN_NOT_FOUND` |
| 409 | `RUN_ALREADY_TERMINAL` |
| 429 | `RATE_LIMITED` |
| 500 | `INTERNAL_ERROR` |
| 503 | `DEPENDENCY_DOWN` |

## Rate limits

| Endpoint | Limite | Bucket |
|---|---|---|
| `POST /v1/events` | 10k events/min/org | Redis |
| `POST /v1/traces` | 1k spans/s/org | Redis |
| `GET /v1/runs` | 60 req/min/user | Redis |
| `POST /v1/replay` | 10 concurrent/org | Redis lock |
| `POST /v1/compare` | 30 req/min/org | Redis |

## Validação

- Pydantic v2 com `model_config = ConfigDict(strict=True, extra="forbid")`.
- Toda request valida contra JSON Schema em `specs/schemas/`.
- Falha de validação = 400 com `code = SCHEMA_INVALID` + diff de campos.

## Versionamento

- Path versionado: `/v1/...` (não header).
- Breaking change na resposta = `/v2/...` (manter `/v1` por 6 meses).
- Breaking = remover campo, mudar tipo, mudar semântica de existente.
- Adição de campo opcional = não-breaking.

## OpenAPI

- Spec canônica em `/openapi.json`.
- Publicada em https://docs.ai-obs.local/openapi.json.
- SDK TypeScript gerado via `openapi-typescript` (commit em monorepo).

## O que este domínio **NÃO** decide

- Quem autentica → `11-auth.md`
- Como UI consome → `10-ui.md`
- Como API é deployada → `12-infra.md`
