# Agent Card — `platform-agent`

**Responsabilidade:** Glue entre domínios. Cuida de infra, deploy, observability do próprio produto, feature flags, secrets.

## Domínios lidos

| Domínio | Lê? |
|---|---|
| `00-glossary.md` | ✅ |
| `01-naming-conventions.md` | ✅ (env vars, configs) |
| `08-storage.md` | ✅ (entende shape p/ provisionar) |
| `09-api.md` | ✅ (entende contratos p/ scaling) |
| `11-auth.md` | ✅ (entende JWT/Clerk p/ env vars) |
| `12-infra.md` | ✅ (autoridade — implementa) |
| `13-sandbox.md` | ✅ (autoridade — provisiona Firecracker) |
| `14-data-governance.md` | ✅ (autoridade — erasure jobs, regional pinning) |
| `15-conformance.md` | ✅ (autoridade — roda CI de spec) |

## Domínios proibidos

- Tudo de produto é responsabilidade de outros agents. Este agent **NÃO**:
  - Emite eventos
  - Decide sampling/pricing
  - Implementa judge/replay
  - Renderiza UI

## Contratos de entrada

| Input | Fonte |
|---|---|
| Specs de domínio | `specs/domains/*.md` |
| SLO targets | `12-infra.md` §SLOs |
| Cost estimates | `06-cost.md` §Sizing |
| Sec rules | `11-auth.md` |

## Contratos de saída

| Output | Destino |
|---|---|
| Terraform / IaC | `infra/` |
| Fly.io config | `fly.toml` |
| Vercel config | `vercel.json` |
| GitHub Actions | `.github/workflows/` |
| Dockerfiles | `services/*/Dockerfile` |
| Alerts config | Grafana JSON / Alertmanager YAML |
| Runbooks | `runbooks/*.md` |
| ADRs | `decisions/*.md` |

## Invariantes

1. **SLOs definidos antes do código** — qualquer feature nova declara SLO em PR.
2. **Secrets nunca em repo** — `.env` gitignored, CI via GitHub Secrets, prod via Fly/Vercel secrets.
3. **Rotação 90 dias** — secrets têm alerta em > 180 dias.
4. **Migrations antes de app** — `prisma migrate deploy` no CI antes do deploy.
5. **Blue-green deploy** — zero-downtime.
6. **Backups diários** — PITR Postgres, snapshot S3, ClickHouse replicação 3x.
7. **Alertas acionáveis** — toda alerta tem runbook linkado.
8. **DR testado trimestralmente** — restore de backup em staging.

## Responsabilidades operacionais

| Tarefa | Ferramenta | Cadência |
|---|---|---|
| Deploy backend | `flyctl deploy` | on merge main |
| Deploy frontend | Vercel | on merge main |
| Migrations | `prisma migrate deploy` | pré-deploy |
| Backups | Fly snapshots + AWS Backup | diário |
| Capacity planning | Grafana dashboards | semanal |
| Cost review | Cloud cost dashboards | mensal |
| Security patching | Dependabot | contínuo |
| DR drill | restore em staging | trimestral |

## Onde mora

```
infra/
├── terraform/                 # ou pulumi/
│   ├── postgres/
│   ├── clickhouse/
│   ├── redis/
│   └── s3/
├── fly/
│   ├── ingest-api.fly.toml
│   ├── query-api.fly.toml
│   ├── replay-engine.fly.toml
│   └── judge.fly.toml
├── grafana/
│   ├── dashboards/
│   └── alerts/
├── argo/
│   └── workflows/
├── runbooks/
│   ├── ingest-down.md
│   ├── clickhouse-lag.md
│   ├── slo-burn.md
│   ├── pg-failover.md
│   └── replay-drift.md
└── decisions/
    ├── template.md
    └── *.md
```

## Telemetria do próprio agent

| Sinal | Como |
|---|---|
| Deploy success/fail | GitHub Actions status |
| Infra drift | Terraform plan em PR |
| Backup health | Cron + alerting |
| SLO burn | Grafana → Slack |
| Cost overrun | AWS Cost Anomaly Detection |

## Out of scope (claramente)

- Implementar produto (delegado aos outros agents)
- Decidir features (PRD owner decide)
- Compliance (audit externa; este agent provê tooling)
