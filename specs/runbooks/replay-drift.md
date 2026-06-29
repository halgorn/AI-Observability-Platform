# Runbook — Replay divergência em massa

## Severidade

- **SEV2** se > 10% dos replays divergem em 1h
- **SEV3** se pattern específico (1 tool ou 1 agent)

## Sintomas

- Alerta: `replay_divergences_total` rate subindo
- Customers reclamando "replay não bate"
- `attributes.replay.diverged=true` em alta proporção

## Diagnóstico

```bash
# 1. Top tools/agents divergentes
# Query ClickHouse:
SELECT
    attributes['replay.diverged'] AS diverged,
    tool,
    count() AS n
FROM events_ch
WHERE type = 'tool.invoke'
  AND started_at > now() - INTERVAL 1 HOUR
  AND attributes['replay.diverged'] = 'true'
GROUP BY tool
ORDER BY n DESC
LIMIT 20;

# 2. Verificar mock config
redis-cli -u $REDIS_URL HGETALL replay:session:<session_id>

# 3. Verificar versão do SDK rodando
# (cada replay inclui sdk version em attributes.genai.sdk.version)
```

## Causas comuns

| Causa | Sinal | Ação |
|---|---|---|
| Mock toggle quebrado | sempre diverge em LLM | verificar `replay:session` Redis |
| Tool side-effect | diverge só em tools com `side_effect=true` | forçar mock de tool |
| Time drift | divergência em `started_at` | corrigir wall clock mock |
| LLM model changed | cache miss + output diff | invalidar cache, documentar |
| Checkpoint corruption | sempre diverge no mesmo step | restore de backup |

## Mitigação

```bash
# 1. Pausar novos replays
fly scale count 0 -a ai-obs-replay

# 2. Investigar root cause
# (ver Causas comuns)

# 3. Aplicar fix
# - corrigir código
# - invalidar cache Redis
# - atualizar mock config

# 4. Reativar
fly scale count 2 -a ai-obs-replay
```

## Comunicação

- Customers: email "replay investigation in progress"
- Status page: SEV2

## Pós-incidente

- [ ] Postmortem se durou > 1h
- [ ] Adicionar regression test no sandbox
- [ ] Revisar `13-sandbox.md` §Determinismo
