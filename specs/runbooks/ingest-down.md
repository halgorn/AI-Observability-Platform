# Runbook — Ingest API down

## Severidade

- **SEV1** se > 5 min sustained
- **SEV2** se degradado (> 50% error rate)

## Sintomas

- Alerta Grafana: `ingest_rejected_total` ou `ingest_latency_seconds` p99 > 1s
- Sentry spike de `INGEST_REJECTED`
- Customers reportando "data missing"

## Diagnóstico (5 min)

```bash
# 1. Health
curl -fsS https://api.ai-obs.local/v1/healthz
curl -fsS https://api.ai-obs.local/v1/readyz

# 2. Logs recentes
fly logs -a ai-obs-ingest --since 10m | head -200

# 3. Dependências
fly status -a ai-obs-ingest
psql $POSTGRES_DSN -c "SELECT 1"
redis-cli -u $REDIS_URL ping
```

## Causas comuns

| Causa | Sinal | Ação |
|---|---|---|
| Postgres unreachable | `pg_is_in_recovery=true` ou connection refused | failover (runbook pg-failover) |
| Redis down | `PING` falha | restart Fly Redis ou trocar pra secondary |
| OTel collector loop | `OTLP rejected` no log | restart collector, drenar queue |
| Deploy quebrado | version mismatch | rollback via `fly releases rollback` |

## Mitigação imediata

```bash
# Rollback para release anterior
fly releases rollback -a ai-obs-ingest

# Escalar horizontalmente
fly scale count 6 -a ai-obs-ingest

# Drenar OTel collector
kubectl delete pod -n otel -l app=otel-collector
```

## Comunicação

- Status page: postar incidente
- Slack `#ai-obs-incidents`: thread único
- Customers > 10 reqs/min: email template

## Pós-incidente

- [ ] Postmortem em `postmortems/YYYY-MM-DD-ingest.md`
- [ ] Blameless review em 48h
- [ ] Atualizar runbook se ações novas
- [ ] Verificar SLO budget consumido
