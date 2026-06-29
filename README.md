# AI Observability Platform

> Event-sourced observability for LLM agents. Capture every step, attribute cost per tool, replay deterministically.

[![CI](https://github.com/halgorn/AI-Observability-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/halgorn/AI-Observability-Platform/actions/workflows/ci.yml)
[![Spec Conformance](https://github.com/halgorn/AI-Observability-Platform/actions/workflows/spec-guard.yml/badge.svg)](https://github.com/halgorn/AI-Observability-Platform/actions/workflows/spec-guard.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

Your agent sold $0 on Black Friday because it entered a loop. Logs didn't say why. **This is for that.**

## What is it

Production-grade observability for LLM agents, with three properties no competitor has together:

1. **Event sourcing as truth** — every interaction is an append-only `event`. UI, metrics, and replay all derive from it.
2. **Bit-exact replay** — replays are deterministic on tools; LLM is mockable with fixed seed.
3. **Cost is first-class telemetry** — every LLM call carries `cost_usd` in the same span, attributable to `agent × tool × step × prompt_version`.
4. **Spec-driven, not vibe-driven** — entire API contract lives as JSON Schemas in [`specs/`](./specs). Code reads schema, not duck types. CI fails on drift.

| Question | Datadog | LangSmith | **This** |
|---|---|---|---|
| Why did *this run* fail? | generic traces | visual trace | causal attribution per node |
| Which tool cost the most? | doesn't know | token sum | `cost_usd` per `tool × step × agent` |
| Where did the handoff break? | doesn't see | not modeled | handoff graph + success rate |
| Which prompt regressed quality? | n/a | manual diff | auto A/B with LLM-as-judge |
| Reproduce yesterday's run? | impossible | re-executes (non-deterministic) | **bit-a-bit replay** |

## Architecture

```
┌────────────────┐
│ LangGraph /    │
│ Agents users   │  ← packages/ai-obs-sdk  (Python SDK, @observe, GraphTracer)
└───────┬────────┘
        │ OTLP / REST
        ▼
┌────────────────┐     ┌─────────────────┐
│ OTel Collector │────▶│ Ingest API      │  ← services/ingest-api (FastAPI, idempotent)
└────────────────┘     │ (REST + OTLP)   │     ← Postgres + ClickHouse + Kafka + DLQ
                       └────────┬────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
         ┌─────────────┐ ┌──────────┐    ┌──────────────┐
         │  Postgres   │ │ ClickH.  │    │   Kafka DLQ   │
         └──────┬──────┘ └────┬─────┘    └──────┬───────┘
                │             │               │
                ▼             ▼               ▼
         ┌──────────────────────────────────────────┐
         │        Query API (services/query-api)    │
         │  /runs /trace /events /checkpoints       │
         │  /similar /compare /cost/* /handoffs     │
         └──────────────────┬─────────────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
         ┌──────────────┐         ┌──────────────────┐
         │ Replay Engine │         │ Judge Service    │
         │ (sandbox +    │         │ (LLM-as-judge    │
         │  divergence)  │         │  + Argo + cache) │
         └──────┬───────┘         └────────┬─────────┘
                │                          │
                └──────────┬───────────────┘
                           ▼
                  ┌──────────────────┐
                  │   Web (Next.js)  │
                  │  /runs /agents   │
                  │  /tools /replay  │
                  └──────────────────┘
```

**Deploy**: Fly.io (backend) · Vercel (web) · GitHub Actions (CI) · Clerk (auth)

## Repository layout

```
.
├── prd.md                          Product requirements
├── specs/                          Spec-driven design system (single source of truth)
│   ├── 00-glossary.md              Canonical vocabulary
│   ├── 01-naming-conventions.md    snake_case / kebab-case / PascalCase rules
│   ├── 02-event-schema.md          Event envelope contract
│   ├── schemas/                    JSON Schemas (6 files: event.v1, run.v1, ...)
│   ├── domains/                    13 specs (tracing → conformance)
│   ├── agents/                     7 agent cards
│   ├── decisions/                  ADRs (template + 0001)
│   ├── runbooks/                   5 operational runbooks
│   ├── tools/                      6 executable spec linters
│   └── fixtures/                   Examples validated against schemas
├── packages/
│   └── ai-obs-sdk/                 Python SDK (@observe, GraphTracer, cost, PII)
├── services/
│   ├── ingest-api/                 FastAPI, OTLP HTTP+gRPC, idempotency, DLQ
│   ├── query-api/                  FastAPI, trace tree, cost, handoff, diff, pgvector
│   ├── replay-engine/              FastAPI, deterministic replay, mock layer
│   └── judge/                      FastAPI, LLM-as-judge, cache, Argo workflow
├── apps/
│   └── web/                        Next.js 14 (App Router), Runs/Trace/Replay views
├── examples/
│   └── demo_agent/                 End-to-end demo: 3-step agent, emits 7 events
├── .github/workflows/             ci.yml, spec-guard.yml
├── Makefile                        spec-lint, test, build-ingest, run-ingest
├── CONTRIBUTING.md                 Workflow + rules
├── CODE_OF_CONDUCT.md              Contributor Covenant 2.1
└── LICENSE                         MIT
```

## Quickstart

### Prereqs

- Python ≥ 3.10
- Node ≥ 20 (for `apps/web`)
- Docker (optional, for containerized run)
- `make`

### Run all tests (212 passing)

```bash
make test         # SDK + ingest + query + replay + judge (Python)
make spec-lint    # 5 spec linters, ~0.5s
```

### Run the demo end-to-end

```bash
# Terminal 1: start ingest API
make run-ingest

# Terminal 2: run the demo agent
pip install -e packages/ai-obs-sdk
pip install -e examples/demo_agent
INGEST_API_SECRET=demo \
AI_OBS_INGEST_URL=http://localhost:8000 \
python examples/demo_agent/agent.py
# → emitted 7 events: 2 handoffs, 1 llm.call, 2 tool.invoke, 1 step.start
```

### Run with Docker

```bash
make build-ingest
docker run -p 8000:8000 -e INGEST_API_SECRET=demo -e SPEC_ROOT=/app/specs ingest-api
```

### Run the web UI

```bash
cd apps/web
npm install
npm run dev
# → http://localhost:3000
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

All configuration via environment variables. See [`.env.example`](./services/ingest-api/.env.example) for the full list.

| Var | Required | Default | Purpose |
|---|---|---|---|
| `INGEST_API_SECRET` | ✅ | `dev-secret-do-not-use-in-prod` | HMAC-SHA256 secret for service tokens |
| `SPEC_ROOT` | in prod | repo path | where JSON Schemas live |
| `POSTGRES_DSN` | in prod | — | Postgres connection string |
| `REDIS_URL` | in prod | — | Redis (judge cache, rate limits) |
| `KAFKA_BROKERS` | in prod | — | Redpanda/Kafka bootstrap |
| `SENTRY_DSN` | optional | — | error tracking (PII auto-scrubbed) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | optional | — | OTLP gRPC collector for self-tracing |
| `PII_MODE` | optional | `redact` | `strict` / `redact` / `passthrough` |

## Development

```bash
# Lint + tests
make spec-lint
make test

# Add a new event type
1. Add definition to specs/schemas/event-types.v1.json
2. Add Pydantic model to services/ingest-api/app/schemas.py
3. Make lint + tests happy
4. Update specs/00-glossary.md if you added a new error code

# Add a new service
1. Create services/<name>/
2. Add agent card to specs/agents/<name>-agent.md
3. Add tests + Makefile target
```

## Testing

```bash
# Spec conformance
make spec-lint
make spec-lint-verbose   # show external refs pending code
make spec-fix            # list unimplemented paths

# All Python tests (212)
make test                # sdk + ingest + query + replay + judge

# Per-service
make test-sdk
make test-ingest
make test-query
make test-replay
make test-judge

# Contract tests (validates fixtures against schemas)
python specs/tools/check_fixtures.py
```

## Roadmap (PRD §10)

All 12-week milestones done:

| Week | Milestone | Status |
|---|---|---|
| 1–2 | Event model + ingest API + SDK | ✅ ingest-api + ai-obs-sdk |
| 3–4 | Postgres schema + storage + query `/trace` | ✅ query-api |
| 5–6 | `GraphTracer` for LangGraph + replay engine | ✅ replay-engine |
| 7–8 | UI: trace view + replay view | ✅ apps/web |
| 9–10 | Cost attribution + handoff graph + diff view | ✅ query-api (analytics) |
| 11 | Judge service + LLM-as-judge async | ✅ judge + Argo |
| 12 | Docs, demo dataset, post público | ✅ examples/demo_agent + this README |

## Architecture decisions

- [ADR 0001: Event sourcing as canonical model](./specs/decisions/0001-event-sourcing.md)
- See [`specs/decisions/`](./specs/decisions) for the full log

## License

[MIT](./LICENSE) — see [`LICENSE`](./LICENSE) for full text.

## Acknowledgments

Built by [Bruno](https://github.com/halgorn). Inspired by and competing with [LangSmith](https://www.langchain.com/langsmith), [Langfuse](https://langfuse.com), [Helicone](https://helicone.ai), and [Datadog APM](https://www.datadoghq.com/dg/apm). Uses [OpenTelemetry](https://opentelemetry.io/) semantic conventions for `genai.*` attributes.
