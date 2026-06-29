# Runbook — Postgres failover

## Severidade

- **SEV1** (postgres primary down)
- **SEV0** se replicação corrompida + sem backup

## Sintomas

- Alerta: `pg_is_in_recovery=true` no primary
- API retorna `DEPENDENCY_DOWN` (503)
- `fly status` mostra postgres unhealthy

## Diagnóstico

```bash
# 1. Status
fly status -a ai-obs-postgres

# 2. Replicação (se HA)
psql $POSTGRES_DSN -c "SELECT * FROM pg_stat_replication;"

# 3. Conexões ativas
psql $POSTGRES_DSN -c "SELECT count(*) FROM pg_stat_activity;"

# 4. Disk usage
fly ssh console -a ai-obs-postgres -C "df -h /data"
```

## Failover manual (Fly Postgres)

```bash
# 1. Listar read replicas
fly postgres list

# 2. Promover replica a primary
fly postgres promote -- replica-name

# 3. Atualizar secrets da app
fly secrets set POSTGRES_DSN="postgres://new-primary:5432/ai_obs" -a ai-obs-ingest
fly secrets set POSTGRES_DSN="..." -a ai-obs-query
fly secrets set POSTGRES_DSN="..." -a ai-obs-replay
fly secrets set POSTGRES_DSN="..." -a ai-obs-judge

# 4. Restart apps para reconectar
fly restart -a ai-obs-ingest
fly restart -a ai-obs-query
fly restart -a ai-obs-replay
fly restart -a ai-obs-judge
```

## Restore de backup (PITR)

```bash
# 1. Listar snapshots
fly postgres backups list

# 2. Restore PITR
fly postgres restore --target-pg pg-restore --timestamp "2026-06-29 12:00:00"

# 3. Validar
psql $POSTGRES_DSN -c "SELECT count(*) FROM events WHERE started_at > '2026-06-29 12:00:00';"
```

## Comunicação

- **SEV1**: postar status page IMEDIATAMENTE
- Customers: email template "database maintenance"
- Slack `#ai-obs-incidents`: thread único

## Pós-incidente

- [ ] Postmortem **obrigatório** (SEV1)
- [ ] Validar RPO/RTO foram respeitados
- [ ] Testar failover em staging (próxima sprint)
- [ ] Avaliar migração para managed Postgres (RDS, Neon) se recorrente
