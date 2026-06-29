# Runbook — SLO burn rate alert

## Severidade

Definida pelo próprio alerta (severidade derivada do burn rate).

## Sintomas

- Alerta Grafana: `SLO <id> burning too fast`
- Multi-window burn: 2% em 1h, 5% em 6h
- Badge "firing" no SLODashboard

## Diagnóstico (10 min)

```bash
# 1. Identificar SLO queimando
# (alerta inclui SLO id e janela)

# 2. Verificar dashboards relevantes
# - /d/ingest-overview
# - /d/trace-query
# - /d/cost-overview

# 3. Correlacionar com deploys
fly releases -a <service>
gh run list --workflow=deploy.yml

# 4. Verificar upstream
fly status -a <service>
```

## Causas comuns

| SLO | Causa provável | Ação |
|---|---|---|
| `availability` | deploy quebrado, dep down | rollback |
| `ingest_overhead_p99` | SDK novo pesado, OTel config ruim | rollback SDK ou ajuste collector |
| `trace_query_p95` | query plan ruim, índice faltando | explain analyze, adicionar índice |
| `judge_latency_p95` | Argo queue, OpenAI slow | scale workers, retry |
| `cost.p95_per_run` | prompt inflation, loop de agente | alerta para user + ver runs afetados |
| `success_rate{agent}` | prompt regression | diff de prompt, rollback |

## Mitigação

```bash
# Rollback do último deploy
fly releases rollback -a <service>

# OU pausar tráfego novo
fly scale count 1 -a <service>
```

## Comunicação

- `#ai-obs-alerts`: responder com thread único
- Status page: SEV2+
- Customers afetados: email proativo

## Pós-incidente

- [ ] Calcular budget consumido: `1 - (current_slo * window)`
- [ ] Postmortem se budget > 10% em < 1h
- [ ] Atualizar runbook específico do SLO se padrão novo
- [ ] Adicionar regression test
