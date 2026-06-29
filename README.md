# AI Observability Platform

> Event-sourced observability for LLM agents. Capture every step, attribute cost per tool, replay deterministically.

[![CI](https://github.com/halgorn/AI-Observability-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/halgorn/AI-Observability-Platform/actions/workflows/ci.yml)
[![Spec Conformance](https://github.com/halgorn/AI-Observability-Platform/actions/workflows/spec-guard.yml/badge.svg)](https://github.com/halgorn/AI-Observability-Platform/actions/workflows/spec-guard.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

Your agent sold $0 on Black Friday because it entered a loop. Logs didn't say why. **This is for that.**

## The problem

LLM agents in production fail in ways that logs and APMs don't capture:

| Question | Datadog | LangSmith | **This** |
|---|---|---|---|
| Why did *this run* fail? | generic traces | visual trace | causal attribution per node |
| Which tool cost the most? | doesn't know | token sum | `cost_usd` per `tool × step × agent` |
| Where did the handoff break? | doesn't see | not modeled | handoff graph + success rate |
| Which prompt regressed quality? | n/a | manual diff | auto A/B with LLM-as-judge |
| Reproduce yesterday's run? | impossible | re-executes (non-deterministic) | **bit-a-bit replay** |

## Why this is different

1. **Event sourcing as truth** — every interaction is an append-only `event`. UI, metrics, and replay all derive from it.
2. **Reproducibility is first-class** — replays are bit-exact on tools; the LLM is mockable with a fixed seed.
3. **Cost is telemetry** — every LLM call carries `cost_usd` in the same span, attributable to `agent × tool × step × prompt_version`.
4. **Spec-driven, not vibe-driven** — the entire API contract lives as JSON Schemas in [`specs/`](./specs). Code reads schema, not duck types. CI fails on drift.

## Demo

```bash
# 1. Run the spec linter (validates JSON Schemas + cross-refs)
make spec-lint

# 2. Start the ingest API
cd services/ingest-api && pip install -e ".[dev,observability]"
INGEST_API_SECRET=demo uvicorn app.main:app --port 8000

# 3. Ingest an event
TOKEN=$(INGEST_API_SECRET=demo python3 -c "from app.auth import TokenStore; print(TokenStore(secret=b'demo').issue('org_demo', ['ingest.write']))")

curl -X POST http://127.0.0.1:8000/v1/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '[{
    "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
    "span_id": "0aaa1bb0c0ffee01",
    "type": "llm.call",
    "agent": "planner",
    "llm_model": "openai/gpt-4o-mini",
    "started_at": "2026-06-29T12:00:00Z",
    "payload": {
      "model": "openai/gpt-4o-mini",
      "messages_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
      "messages_size": 1,
      "finish_reason": "stop"
    }
  }]'
# → {"accepted": 1, "rejected": 0, "rejected_details": []}
```

## Architecture

```
┌────────────────┐
│ LangGraph /    │
│ Agents users   │
└───────┬────────┘
        │ OpenTelemetry SDK (ai-obs-sdk)
        ▼
┌────────────────┐     OTLP      ┌─────────────────┐
│ OTel Collector │──────────────▶│ Ingest API      │  ← you are here
└────────────────┘               │ FastAPI + Pydantic v2
                                └────────┬────────┘
                                         │
                       ┌─────────────────┼─────────────────┐
                       ▼                 ▼                 ▼
                ┌─────────────┐   ┌─────────────┐   ┌──────────┐
                │  Redpanda   │   │  Postgres   │   │  Redis   │
                │  (buffer)   │   │ events+ckpt │   │ (cache)  │
                └──────┬──────┘   └──────┬──────┘   └────┬─────┘
                       ▼                 ▼               │
                ┌─────────────┐   ┌─────────────┐        │
                │ ClickHouse  │   │   Tempo     │        │
                └──────┬──────┘   └──────┬──────┘        │
                       │                 │               │
                       └────────┬────────┴───────────────┘
                                ▼
                       ┌──────────────────┐
                       │ Judge Worker     │  Argo Workflows
                       │ LLM-as-judge     │  + cache by hash
                       └────────┬─────────┘
                                ▼
                       ┌──────────────────┐
                       │  Query API       │  FastAPI
                       │  + Web UI        │  Next.js + React Flow
                       └──────────────────┘
```

**Deploy**: Fly.io (backend) · Vercel (frontend) · GitHub Actions (CI) · Clerk (auth)

## Repository layout

```
.
├── prd.md                          Product requirements
├── specs/                          Spec-driven design system (single source of truth)
│   ├── README.md                   How to read the spec
│   ├── 00-glossary.md              Canonical vocabulary
│   ├── 01-naming-conventions.md    snake_case / kebab-case / PascalCase rules
│   ├── 02-event-schema.md          Event envelope contract
│   ├── schemas/                    JSON Schemas (event.v1, run.v1, etc.)
│   ├── domains/                    03-tracing → 15-conformance (13 specs)
│   ├── agents/                     Cards per executing agent
│   ├── decisions/                  ADRs (template + 0001)
│   ├── runbooks/                   5 operational runbooks
│   ├── tools/                      5 executable spec linters
│   └── fixtures/                   Examples validated against schemas
└── services/
    └── ingest-api/                 First service — production-ready
        ├── app/                    18 modules, ~2k LOC
        ├── tests/                  66 tests, 86% coverage
        ├── Dockerfile              Multi-stage, non-root
        ├── fly.toml                Deploy config (blue/green)
        ├── observability/          Prometheus + alerts
        └── README.md
```

## Quickstart

### Prereqs

- Python ≥ 3.10
- Node ≥ 20 (for SDK and web, coming)
- Docker (optional, for containerized run)
- `make`

### Run the spec linter

```bash
make spec-lint
```

Validates all JSON Schemas, cross-references, and enum consistency. No install needed beyond `pip install jsonschema`.

### Run the ingest API

```bash
cd services/ingest-api
pip install -e ".[dev]"
pytest tests/ --cov=app               # 66 tests, ~1.7s

INGEST_API_SECRET=demo uvicorn app.main:app --port 8000
```

Open <http://localhost:8000/docs> for interactive Swagger.

### Run with Docker

```bash
docker build -t ingest-api -f services/ingest-api/Dockerfile .
docker run -p 8000:8000 -e INGEST_API_SECRET=demo -e SPEC_ROOT=/app/specs ingest-api
```

### Deploy to Fly.io

```bash
cd services/ingest-api
fly launch --copy-config --no-deploy
fly secrets set INGEST_API_SECRET=$(openssl rand -base64 32)
fly secrets set POSTGRES_DSN=... REDIS_URL=... KAFKA_BROKERS=...
fly deploy
```

See [`services/ingest-api/README.md`](./services/ingest-api/README.md) for full config.

## Configuration

All configuration via environment variables. See [`services/ingest-api/.env.example`](./services/ingest-api/.env.example) for the full list.

| Var | Required | Default | Purpose |
|---|---|---|---|
| `INGEST_API_SECRET` | ✅ | `dev-secret-do-not-use-in-prod` | HMAC-SHA256 secret for service tokens |
| `SPEC_ROOT` | in prod | repo path | where JSON Schemas live |
| `POSTGRES_DSN` | ✅ in prod | — | Postgres connection string |
| `REDIS_URL` | ✅ in prod | — | Redis (judge cache, rate limits) |
| `KAFKA_BROKERS` | ✅ in prod | — | Redpanda/Kafka bootstrap |
| `SENTRY_DSN` | optional | — | error tracking (PII auto-scrubbed) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | optional | — | OTLP gRPC collector for self-tracing |
| `PII_MODE` | optional | `redact` | `strict` / `redact` / `passthrough` |

## Development

```bash
# Lint + tests
make spec-lint
make test-ingest

# Add a new event type
1. Add definition to specs/schemas/event-types.v1.json
2. Add Pydantic model to services/ingest-api/app/schemas.py
3. Make lint + tests happy
4. Update specs/00-glossary.md if you added a new error code

# Add a new service
1. Create services/<name>/
2. Add agent card to specs/agents/<name>-agent.md
3. Add to .github/workflows/ci.yml
```

See [`specs/domains/15-conformance.md`](./specs/domains/15-conformance.md) for the full conformance contract (versioning, sunset, contract tests).

## Testing

```bash
# Spec conformance (no code)
make spec-lint
make spec-lint-verbose   # show external refs pending code
make spec-fix            # list unimplemented paths

# Ingest API
make test-ingest         # 66 tests, 86% coverage

# Contract tests (validates fixtures against schemas)
python specs/tools/check_fixtures.py
```

## Roadmap

| Week | Milestone | Status |
|---|---|---|
| 1–2 | Event model + ingest API + `@observe` SDK | 🟡 ingest-api done, SDK pending |
| 3–4 | Postgres schema + storage + query `/trace` | ⏳ query-api pending |
| 5–6 | `GraphTracer` for LangGraph + replay engine | ⏳ replay-engine pending |
| 7–8 | UI: trace view + replay view | ⏳ apps/web pending |
| 9–10 | Cost attribution + handoff graph + diff view | ⏳ |
| 11 | Judge service + LLM-as-judge async | ⏳ judge-service pending |
| 12 | Docs, demo dataset, public post | ⏳ |

See [`prd.md`](./prd.md) for full PRD.

## Contributing

PRs welcome. Before opening one:

1. Run `make spec-lint` — your change must not break cross-references.
2. Run `make test-ingest` — your change must keep tests green and coverage ≥ 80%.
3. If you changed a schema, update the version (`.v2`) and add an ADR in `specs/decisions/`.
4. If you added an error code, update `specs/00-glossary.md` and `specs/schemas/event.v1.json#/$defs/ErrorCode` together.

CODEOWNERS in [`specs/domains/15-conformance.md`](./specs/domains/15-conformance.md) — domain owners must approve changes to their domain.

## Architecture decisions

- [ADR 0001: Event sourcing as canonical model](./specs/decisions/0001-event-sourcing.md)

## License

[MIT](./LICENSE) — see [`LICENSE`](./LICENSE) for full text.

## Acknowledgments

Built by [Bruno](https://github.com/halgorn). Inspired by and competing with [LangSmith](https://www.langchain.com/langsmith), [Langfuse](https://langfuse.com), [Helicone](https://helicone.ai), and [Datadog APM](https://www.datadoghq.com/dg/apm). Uses [OpenTelemetry](https://opentelemetry.io/) semantic conventions for `genai.*` attributes.
