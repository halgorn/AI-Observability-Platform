# Runbook — ClickHouse lag

## Severidade

- **SEV2** se lag > 5 min sustained
- **SEV3** se lag > 30 min sustained (analytics degradado, prod não)

## Sintomas

- Alerta: `ingest_clickhouse_lag_seconds > 300`
- Dashboards mostrando dados defasados
- Queries de cost em ClickHouse incompletas

## Diagnóstico

```bash
# 1. Lag real
SELECT now() - max(started_at) AS lag
FROM events_ch FINAL;

# 2. Consumer status
fly status -a ai-obs-clickhouse-consumer
fly logs -a ai-obs-clickhouse-consumer --since 10m | head -200

# 3. Redpanda lag
kafka-consumer-groups --bootstrap-server $KAFKA --describe --group ch-mirror

# 4. ClickHouse health
clickhouse-client --query "SELECT version(), uptime()"
```

## Causas comuns

| Causa | Sinal | Ação |
|---|---|---|
| Consumer crashed | pod em `CrashLoopBackOff` | restart, verificar erro |
| Backpressure | lag crescendo em consumer | scale consumer (`fly scale count`) |
| ClickHouse overload | `system.merges` alto, queries lentas | reduzir partition, ou upsize |
| Kafka lag | `LAG` grande em `ch-mirror` | commit offsets, verificar poison messages |

## Mitigação

```bash
# Escalar consumer
fly scale count 4 -a ai-obs-clickhouse-consumer

# Pular mensagens ruins (se houver)
kafka-consumer-groups --bootstrap-server $KAFKA \
    --group ch-mirror --reset-offsets --to-current --topic events.raw

# Force merge se ClickHouse overloaded
clickhouse-client --query "OPTIMIZE TABLE events_ch FINAL"
```

## Comunicação

- Analytics team: avisar que dashboards podem estar atrasados
- Status page: note "analytics delayed"

## Pós-incidente

- [ ] Verificar se SLO `query_p95` foi afetado (não deveria, vai em Postgres)
- [ ] Avaliar autoscaling do consumer
- [ ] Postmortem se durou > 30 min
