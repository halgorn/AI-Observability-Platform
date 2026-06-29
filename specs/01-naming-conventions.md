# 01 — Naming Conventions

Regras de naming. Aplicam-se a **código, dados, API e UI**.

> Nomes inconsistentes = ruído em agregação. Toda métrica, filtro e coluna deriva destes padrões.

## 1. snake_case (dados, eventos, SQL, JSON)

- Campos JSON: `run_id`, `parent_span_id`, `started_at`, `cost_usd`
- Colunas Postgres: `run_id`, `tokens_in`, `tokens_out`
- Valores enum: `succeeded`, `failed`, `timeout` (minúsculo, singular quando substantivo, verbo no passado)
- Filhos de path: `attributes.llm.model`, `attributes.tool.name`

## 2. kebab-case (URLs, paths, filenames)

- Endpoints: `/runs`, `/runs/{id}/trace`, `/runs/{id}/replay`
- Filenames Python: `graph_tracer.py`, `judge_service.py`
- Filenames TS/Next: `trace-view.tsx`, `handoff-graph.tsx`
- Env vars snake_case em código, kebab-case em compose/k8s (ver `12-infra.md`)

## 3. PascalCase (tipos, classes, componentes)

- Pydantic models: `RunEvent`, `SpanPayload`, `JudgeResult`
- Componentes React: `TraceView`, `HandoffGraph`, `ReplayStepper`
- Classes Python: `GraphTracer`, `ReplayEngine`, `JudgeService`

## 4. SCREAMING_SNAKE (constantes, enums, envs)

- Python: `MAX_SPAN_PAYLOAD_BYTES`, `DEFAULT_SAMPLE_RATE`
- Env vars: `OTEL_EXPORTER_OTLP_ENDPOINT`, `POSTGRES_DSN`
- Headers HTTP: `X-Run-Id`, `X-Org-Id`

## 5. Identificadores canônicos (imutáveis)

| Coisa | Formato | Exemplo |
|---|---|---|
| `run_id` | UUID v7 | `019065a1-7c8e-7xxx-xxxx-xxxxxxxxxxxx` |
| `span_id` | OTLP 16 bytes hex | `0aaa1bb0c0ffee01` |
| `agent` | `[a-z0-9_-]{1,64}` | `planner`, `security-reviewer` |
| `tool` | `[a-z0-9_.-]{1,64}` | `browser.fetch`, `search.web` |
| `llm.model` | `provider/name` | `openai/gpt-4o-mini` |
| `prompt.version` | semver | `v3.1.0` |
| `artifact.hash` | sha256 hex (64 chars) | `9f86d081...` |
| `error.code` | SCREAMING_SNAKE | `TOOL_TIMEOUT` |

## 6. Nomes de agente

- Derivado do **papel**, não do modelo: `planner`, `executor`, `reviewer`, `critic`
- Multi-tenant-safe: prefixo de org **só** em rotas, nunca no `agent` em si
- Reservados: `__system__`, `__replay__` (prefixo duplo underscore = uso interno)

## 7. Nomes de métrica (Prometheus / ClickHouse)

Padrão: `<domínio>_<unidade>_<agregação>`

```
run_duration_seconds_sum
run_duration_seconds_bucket
llm_tokens_total{agent,model,direction}
tool_invocations_total{tool,agent,status}
cost_usd_total{agent,model,tool}
handoff_success_ratio{from,to}
judge_score{agent,model,dimension}
```

- Sufixo `_total` = counter monotônico
- Sufixo `_ratio` / `_rate` = gauge derivado
- Sem sufixo + unidade no nome = gauge

## 8. Nomes de span (OTel)

```
<agent>.<action>
<tool>.<action>
handoff.<from>_to_<to>
judge.<dimension>
```

Exemplos:
- `planner.think`
- `tool.browser_fetch.invoke`
- `handoff.planner_to_executor`
- `judge.factuality`

> Span name **nunca** inclui `run_id` (já está no `trace_id`).

## 9. Nomes de feature flag

`<domínio>.<subdomínio>.<nome>`

```
ingest.otlp.enabled
replay.deterministic.mock_llm
judge.cache.enabled
ui.handoff_graph.colors
```

Default = conservador (mais sampling, mais cache, menos mock).

## 10. Proibições

- ❌ camelCase em JSON/Postgres
- ❌ kebab-case em Python
- ❌ Abreviar `agent` como `ag`, `a`
- ❌ Plural em nomes de enum (`status=faileds`)
- ❌ Usar mesmo nome p/ domínio e instância (`run` table, `run` status)
- ❌ Hard-code UUID/MD5 fora de testes
