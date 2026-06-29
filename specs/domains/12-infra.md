# 12 — Infra Domain

Deploy, CI/CD, SLOs, monitoramento do próprio produto.

## Ambientes

| Env | Backend | Frontend | DB | Propósito |
|---|---|---|---|---|
| `dev` | Fly.io (1× shared-cpu) | Vercel preview | Postgres local + Redis local | loops de dev |
| `staging` | Fly.io (3× regions) | Vercel preview | Postgres + ClickHouse + Redis | QA, demos, load test |
| `prod` | Fly.io (autoscale, multi-region) | Vercel prod | Postgres HA + ClickHouse Cloud + Upstash Redis | produção |

## Deploy

### Backend (FastAPI)

- **Fly.io** com `fly.toml` por região.
- Dockerfile multi-stage: `python:3.12-slim` → `pip install --user`.
- Autoscaling por CPU + RPS.
- Health checks: `/v1/healthz` (liveness) + `/v1/readyz` (readiness, checa DB).
- Secrets via `fly secrets set`: `POSTGRES_DSN`, `REDIS_URL`, `CLERK_*`, `S3_*`.

### Frontend (Next.js)

- **Vercel**, project linked ao monorepo.
- Build command: `pnpm build`.
- Env vars: `NEXT_PUBLIC_API_URL`, `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`.
- Edge functions só para middleware de auth (latência).

## CI/CD

```yaml
# .github/workflows/ci.yml (resumo)
on: [push, pull_request]
jobs:
  lint:    { run: ruff + mypy + eslint }
  test:    { run: pytest + playwright }
  build:   { run: docker build (backend) + next build (frontend) }
  deploy:
    if: main && all_passed
    steps:
      - flyctl deploy --strategy bluegreen
      - vercel deploy --prod
```

- PR → preview deploy (Vercel + Fly staging).
- Merge main → prod.
- Migrations Postgres: `prisma migrate deploy` antes do app.

## SLOs (PRD §6 + §5.5)

| SLO | Target | Janela | Burn rate alert |
|---|---|---|---|
| `availability` | 99.5% | 30d | 2% budget em 1h, 5% em 6h |
| `ingest_overhead_p99` | < 5% latência adicional | 7d | 14.4× em 1h |
| `trace_query_p95` | < 300ms | 7d | 2× sustained 10m |
| `judge_latency_p95` | < 5min enqueue→result | 7d | 2× sustained 30m |
| `cost.p95_per_run{agent}` | < $0.05 | 7d | 1.5× sustained 1h |
| `handoff_success` | > 0.85 | 7d | abaixo por 1h |
| `success_rate{agent}` | > 0.9 | 7d | abaixo por 1h |

## Alertas

- Canal: Slack `#ai-obs-alerts` + webhook.
- Severidade:
  - `p1` (page): SLO queimando > 10% budget em < 1h
  - `p2` (slack): breach de SLO sustentado
  - `p3` (digest diário): warning trends
- Source: Grafana Cloud → Alertmanager → Slack.

## Observability do próprio produto (PRD §0)

| Sinal | Tool | Por quê |
|---|---|---|
| Erros de app | **Sentry** | SOTA Python/TS, free tier generoso |
| Session replay | **Highlight.io** | debugging de UI bugs raros |
| Metrics | Prometheus + Grafana Cloud | já usado p/ SLOs |
| Logs | Grafana Loki (ou CloudWatch) | unified com metrics |
| Uptime | BetterUptime (externo) | evita monitorar a si mesmo |
| APM | OpenTelemetry → Tempo | dogfooding |

## Capacidade

| Recurso | Baseline | Auto-scale até | Custo/mês est. |
|---|---|---|---|
| Fly machines | 2 | 20 | $50 → $500 |
| Postgres (Fly) | 1× shared | 1× dedicated-8 | $30 → $250 |
| ClickHouse Cloud | Production-1 | Production-4 | $200 → $1500 |
| Upstash Redis | Pay-as-you-go | Pro 10GB | $0 → $100 |
| S3 | 100 GB | 10 TB | $3 → $300 |
| Vercel | Pro | Enterprise | $20/seat |
| Grafana Cloud | Free | Pro 10k series | $0 → $300 |
| **Total v1 launch** | | | **~$300-500/mês** |

## Secrets management

- **Dev:** `.env` local (gitignored).
- **CI:** GitHub Actions secrets.
- **Staging/Prod:** Fly secrets + Vercel env.
- **Rotação:** 90 dias, automatizado via `make rotate-secrets`.

## Feature flags

- Provider: **PostHog** (OSS) ou **LaunchDarkly**.
- Default = conservador; flag = opt-in.
- Flags vivem em `feature_flags` table + cache Redis.

## Runbooks canônicos

| Cenário | Runbook |
|---|---|
| Ingest API down | `runbooks/ingest-down.md` |
| ClickHouse lag | `runbooks/clickhouse-lag.md` |
| SLO budget queimando | `runbooks/slo-burn.md` |
| Postgres failover | `runbooks/pg-failover.md` |
| Replay divergência em massa | `runbooks/replay-drift.md` |

## ADR (Architecture Decision Records)

Toda decisão de infra com impacto > 1 mês de trabalho vira ADR em `decisions/`:

```
decisions/
├── 0001-postgres-vs-mongo.md
├── 0002-redpanda-vs-kafka.md
├── 0003-argo-vs-temporal.md
└── ...
```

Template em `decisions/template.md` (em `specs/decisions/`).

## O que este domínio **NÃO** decide

- Schema de dados → `08-storage.md`
- Contrato de API → `09-api.md`
- Quem acessa o quê → `11-auth.md`
