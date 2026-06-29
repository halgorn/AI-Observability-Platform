# ingest-api

Receives observability data from LLM agents. Spec-driven, validated against `specs/schemas/`.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/v1/healthz` | open | liveness |
| `GET` | `/v1/readyz` | open | readiness — checks Postgres, Redis, Kafka |
| `POST` | `/v1/events` | service token | ingest our `Event` shape |
| `POST` | `/v1/traces` | service token | ingest OTLP HTTP (auto-translates to `Event`) |
| `GET` | `/metrics` | open | Prometheus |
| `GET` | `/docs` | open (toggle via `DOCS_ENABLED`) | Swagger UI |

## Quickstart

```bash
# 1. Install
pip install -e ".[dev,observability]"

# 2. Run tests
pytest tests/ --cov=app

# 3. Run live
INGEST_API_SECRET=test-secret uvicorn app.main:app --port 8000

# 4. Test
TOKEN=$(INGEST_API_SECRET=test-secret python3 -c "from app.auth import TokenStore; print(TokenStore(secret=b'test-secret').issue('org_1', ['ingest.write']))")
curl -X POST http://127.0.0.1:8000/v1/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '[{"run_id":"019065a1-7c8e-7abc-9def-1234567890ab","span_id":"0aaa1bb0c0ffee01","type":"llm.call","started_at":"2026-06-29T12:00:00Z","payload":{"model":"openai/gpt-4o-mini","messages_hash":"sha256:0000000000000000000000000000000000000000000000000000000000000000","messages_size":1,"finish_reason":"stop"}}]'
```

## Docker

```bash
docker build -t ingest-api -f services/ingest-api/Dockerfile services/ingest-api
docker run -p 8000:8000 \
  -e INGEST_API_SECRET=test \
  -e SPEC_ROOT=/app/specs \
  ingest-api
```

## Deploy to Fly.io

```bash
cd services/ingest-api
flyctl launch --copy-config --no-deploy
flyctl secrets set INGEST_API_SECRET="$(openssl rand -base64 32)"
flyctl secrets set POSTGRES_DSN="postgres://..."
flyctl secrets set REDIS_URL="redis://..."
flyctl secrets set KAFKA_BROKERS="..."
flyctl deploy
```

## Observability

- **Health**: `/v1/readyz` returns 200 if all deps healthy, 503 if any degraded
- **Metrics**: `/metrics` exposes Prometheus metrics (latency, status, request count)
- **Tracing**: OTLP gRPC to `OTEL_EXPORTER_OTLP_ENDPOINT` (set to collector URL)
- **Errors**: Sentry via `SENTRY_DSN` (PII auto-scrubbed)
- **Logs**: structured JSON to stdout, picked up by Fly logs

## Configuration

See `.env.example` for full list. Key vars:

| Var | Default | Purpose |
|---|---|---|
| `INGEST_API_SECRET` | `dev-secret-do-not-use-in-prod` | HMAC-SHA256 secret for service tokens |
| `PII_MODE` | `redact` | `strict` (reject) / `redact` / `passthrough` |
| `SPEC_ROOT` | `<repo>/specs` | where JSON Schemas live |
| `SENTRY_DSN` | empty | Sentry project DSN |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | OTLP collector gRPC URL |

## Architecture (this service)

```
HTTP request
   ↓
auth (Bearer token, scope check)
   ↓
JSON Schema validation (envelope + payload by type)
   ↓
PII scan (3 modes)
   ↓
Idempotent insert (run_id, span_id)
   ↓
Publish to bus (Redpanda in prod)
   ↓
Return {accepted, rejected, rejected_details}
```

## Spec compliance

- Envelope validated against `specs/schemas/event.v1.json`
- Payload sub-shape validated against `specs/schemas/event-types.v1.json`
- Attributes whitelist enforced (stricter than JSON Schema, by Pydantic)
- Every rejected event includes `code` matching `specs/00-glossary.md#erros-errorcode`

## Testing

```bash
make test-ingest     # from repo root
# or
pytest tests/ --cov=app --cov-fail-under=80
```

Current: 66 tests, 86% coverage. CI: `.github/workflows/ci.yml`.
