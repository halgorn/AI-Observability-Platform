# 06 — Cost Domain

Custo é **telemetria de primeira classe**, não afterthought.

## Modelo

```
cost_usd(run) = Σ cost_usd(event.type = 'llm.call', in run)
              = Σ f(model, tokens_in, tokens_out, ts)
```

## Pricing table

```yaml
# config/pricing.yaml
models:
  openai/gpt-4o-mini:
    input_per_1k_usd:   0.000150
    output_per_1k_usd:  0.000600
    cached_input_per_1k_usd: 0.000075
    effective_from: 2025-01-01
  openai/gpt-4o:
    input_per_1k_usd:   0.002500
    output_per_1k_usd:  0.010000
    effective_from: 2025-01-01
  anthropic/claude-3-5-sonnet:
    input_per_1k_usd:   0.003000
    output_per_1k_usd:  0.015000
    effective_from: 2025-01-01
```

- Pricing versionado: toda mudança cria `pricing.vN` com `effective_from`.
- Lookup por `(model, effective_from ≤ ts)`.

## Cálculo

```python
def cost_of_call(model: str, tokens_in: int, tokens_out: int, at: datetime, cached: bool) -> Decimal:
    p = pricing_for(model, at)
    in_rate  = p.cached_input_per_1k_usd if cached else p.input_per_1k_usd
    return Decimal(tokens_in)  / 1000 * Decimal(in_rate) \
         + Decimal(tokens_out) / 1000 * Decimal(p.output_per_1k_usd)
```

- Resultado sempre em `Decimal(12, 8)`.
- Arredondamento: 8 casas (sub-centavo).

## Onde calcular

| Camada | Quando | Por quê |
|---|---|---|
| SDK | no `llm.call` end | latência mínima |
| Replay | não calcula (LLM mockado) | zero, por design |
| Backfill | em job Argo noturno | correção retroativa se pricing mudou |

> SDK é a fonte da verdade. Backfill reconcilia divergências.

## Atribuição (cost attribution)

Cost é atribuído por 3 eixos:

```
{agent, tool, llm_model} × {step} × {prompt_version}
```

- Agregação padrão: `cost_usd_total{agent, llm_model, prompt_version}` agrupado por `since`.
- Drill-down: `run_id` → lista de spans → soma.
- Top tools (PRD UC2): `ORDER BY sum(cost_usd) DESC LIMIT 10`.

## Storage

- Postgres: `events.cost_usd` (NUMERIC 12,8) — fonte de verdade transacional.
- ClickHouse: `cost_usd Float64` materializado — agregado barato.
- ClickHouse view `cost_by_day`:

```sql
CREATE VIEW cost_by_day AS
SELECT
    toDate(started_at) AS day,
    agent,
    llm_model,
    prompt_version,
    sum(cost_usd) AS cost_usd_total,
    sum(tokens_in) AS tokens_in_total,
    sum(tokens_out) AS tokens_out_total
FROM events
WHERE type = 'llm.call'
GROUP BY day, agent, llm_model, prompt_version;
```

## SLO de custo

Definido em `12-infra.md`:

```yaml
slos:
  - id: cost.p95_per_run
    expr: histogram_quantile(0.95, sum(rate(run_cost_usd_bucket[5m])) by (le, agent))
    target: 0.05   # USD
  - id: cost.daily_budget
    expr: sum(increase(cost_usd_total[1d]))
    target: 1000.0 # USD
```

## Visualização (PRD §5.4)

- **Waterfall** por run: bar chart horizontal, um bar por step.
- **Top tools** semanal: leaderboard.
- **Heatmap** `tool × prompt_version`: célula color = `sum(cost_usd) / count`.
- **Diff** entre 2 runs: side-by-side, com `Δ` em USD e %.

## Edge cases

| Caso | Tratamento |
|---|---|
| LLM call falhou (sem tokens) | `cost_usd = 0`, mas emite evento com `error_code` |
| Modelo desconhecido | `cost_usd = NULL`, alerta para pricing desatualizado |
| Tokens reportados pelo user (não API) | aceitar se bater com `usage` field, senão `NULL` |
| Replay | `cost_usd = 0` (não conta em prod) |
| Currency != USD | converter via FX diário; UI mostra USD canônico + original |

## O que este domínio **NÃO** decide

- Quem vê o quê → `11-auth.md`
- Como alertas disparam → `12-infra.md`
