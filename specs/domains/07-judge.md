# 07 — Judge Domain

LLM-as-judge **assíncrono** com cache agressivo.

## Quando julgar

| Trigger | Condição | Modelo |
|---|---|---|
| `error` event | sempre | `judge.error_severity` |
| `succeeded` | prompt_version mudou (A/B) | `judge.prompt_diff` |
| `succeeded` | score histórico < 0.5 | `judge.low_score_followup` |
| Manual | `POST /score { run_id, dimensions }` | qualquer |

Default: **não** julgar runs de produção bem-sucedidas sem trigger. Custo controlado.

## Dimensões canônicas

```python
JUDGE_DIMENSIONS = Literal[
    "factuality",     # ground-truth check
    "relevance",      # output vs input intent
    "harmfulness",    # safety / policy
    "coherence",      # estrutura do raciocínio
    "completeness",   # cobriu todos os subgoals
]
```

## JudgeService — contrato

```python
class JudgeService:
    async def enqueue(self, run_id: UUID, dimensions: list[str]) -> JobId: ...
    async def get(self, run_id: UUID) -> list[JudgeResult]: ...
    async def compare(self, run_a: UUID, run_b: UUID, dim: str) -> Comparison: ...
```

- `enqueue` é fire-and-forget; retorna `JobId` para polling.
- Job roda em **Argo Workflows** (PRD §8) — `JudgeService` é o client.
- `get` lê do Postgres (`judge_results` table).

## Cache

```python
def cache_key(model: str, input: str, output: str) -> str:
    return f"judge:{model}:{sha256((input + output).encode()).hexdigest()}"
```

- Lookup em Redis, TTL 30 dias.
- Hit ratio esperado: **≥ 40%** em produção normal.
- Cache invalidado por **manual flush** ou **model change**.

## Tabela `judge_results`

```sql
CREATE TABLE judge_results (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID         NOT NULL,
    span_id     BYTEA        NULL,
    dimension   TEXT         NOT NULL,
    model       TEXT         NOT NULL,
    score       NUMERIC(3,2) NOT NULL CHECK (score BETWEEN 0 AND 1),
    rationale   TEXT         NULL,
    cache_hit   BOOLEAN      NOT NULL DEFAULT false,
    judged_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (run_id, span_id, dimension, model)
);

CREATE INDEX idx_judge_results_run ON judge_results(run_id);
```

## Prompt do judge (template)

```
Você é um avaliador objetivo de um agente de IA.
Compare o output ao input e à definição de qualidade abaixo.

[INPUT]
{input}

[OUTPUT]
{output}

[DIMENSÃO: {dimension}]
{definicao_da_dimensao}

Responda APENAS em JSON:
{
  "score": <float 0.0-1.0>,
  "rationale": "<uma frase, máx 200 chars>"
}
```

> Prompt versionado em `artifacts`, hash vinculado ao `judge_results.prompt_version`.

## Comparação A/B (PRD UC4)

```
POST /compare
{
  "run_a": "uuid",
  "run_b": "uuid",
  "dimension": "factuality"
}

→ 200 OK
{
  "dimension": "factuality",
  "run_a": { "score": 0.72, "model": "gpt-4o-mini", "judged_at": "..." },
  "run_b": { "score": 0.81, "model": "gpt-4o-mini", "judged_at": "..." },
  "delta": 0.09,
  "winner": "run_b",
  "ci_95": [0.04, 0.14],
  "n_judges": 3
}
```

- Default: **3 judges paralelos** com mesma model + temperature 0.7 → média.
- CI por boostrap (n=1000 resamples).

## SLO do judge

| Métrica | Meta |
|---|---|
| Latência p95 (run enqueue → result) | < 5 min |
| Cache hit rate | ≥ 40% |
| Custo médio por judge call | < $0.001 |
| Agreement (judges paralelos, stddev) | < 0.1 |

## Erros

| Cenário | `error.code` | Recovery |
|---|---|---|
| Judge model timeout | `LLM_TIMEOUT` | retry 2x, depois marca `unknown` |
| Judges discordam (stddev > 0.3) | `JUDGE_DISAGREEMENT` | alerta, score = mediana |
| Schema inválido do judge | `LLM_INVALID_OUTPUT` | re-prompt com correção, 1x |

## O que este domínio **NÃO** decide

- Como alertas disparam → `12-infra.md`
- Quem dispara trigger de A/B → `09-api.md`
- Onde resultados aparecem na UI → `10-ui.md`
