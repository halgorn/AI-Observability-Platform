# Agent Card — `judge-agent`

**Responsabilidade:** LLM-as-judge assíncrono com cache, comparação A/B.

## Domínios lidos

| Domínio | Lê? |
|---|---|
| `00-glossary.md` | ✅ |
| `01-naming-conventions.md` | ✅ |
| `02-event-schema.md` | ✅ (lê eventos; emite `judge.result`) |
| `06-cost.md` | ✅ (orçamento de judge) |
| `07-judge.md` | ✅ (autoridade — implementa o que está aqui) |
| `08-storage.md` | ✅ (tabela `judge_results`, Redis cache) |
| `09-api.md` | ✅ (endpoints `POST /v1/score`, `GET /v1/runs/{id}/judge`, `POST /v1/compare`) |
| `14-data-governance.md` | ✅ (PII em rationale, retention) |
| `15-conformance.md` | ✅ (contract tests) |

## Domínios proibidos

- `03-tracing.md`, `04-agent-orchestration.md` — não emite spans de runtime (usa `__judge__` agent)
- `05-replay.md` — pode ser invocado **após** replay, mas não coordena replay
- `10-ui.md`, `11-auth.md` (parcial), `12-infra.md` — não toca UI/auth/infra direto (só consome config)
- `13-sandbox.md` — judge não roda código de usuário

## Contratos de entrada

| Input | Fonte | Validação |
|---|---|---|
| `run_id` | API | UUID v7, exists |
| `dimensions` | API | subset de `JUDGE_DIMENSIONS` |
| `Event` data | Postgres `events` | shape canônico |
| Artifacts (LLM I/O) | S3 | sha256 verified |
| Pricing config | `06-cost.md` (read-only) | — |

```python
class JudgeRequest(BaseModel):
    run_id: UUID
    span_id: str | None = None     # None = judge run-level
    dimensions: list[Literal[
        "factuality","relevance","harmfulness","coherence","completeness"
    ]]
    n_judges: int = Field(default=3, ge=1, le=5)

class CompareRequest(BaseModel):
    run_a: UUID
    run_b: UUID
    dimension: str
    n_judges: int = 3
```

## Contratos de saída

| Output | Destino | Schema |
|---|---|---|
| `judge_results` row | Postgres | `schemas/judge-result.v1.json` |
| `events.type = judge.result` | OTel collector | `02-event-schema.md` |
| `Comparison` | API response | Pydantic v2 |
| Job status (polling) | Argo Workflows | webhook → Redis |

## Invariantes

1. **Assíncrono** — `enqueue` retorna `job_id` imediato, resultado via polling.
2. **Cache key determinístico** — `sha256(model || canonical_json(input) || canonical_json(output))`.
3. **TTL de cache = 30 dias** — invalidação só manual ou em `model change`.
4. **N judges paralelos por default (3)** — score final = média, CI via bootstrap n=1000.
5. **Discordância alta (stddev > 0.3) → `JUDGE_DISAGREEMENT` + score = mediana** — alerta.
6. **Não julga replay** — a menos que explicitamente invocado.
7. **Judge é `__judge__` agent** — spans não contam em métricas de prod cost.
8. **Prompt versionado** — `artifacts.prompt_version` referenciado no `judge_results`.
9. **Org isolation** — judge só roda em runs do mesmo `org_id` do requester.
10. **Audit log** — `action = judge.enqueue` com `actor_id`, `run_id`, `dimensions`.

## Dimensões e modelos

| Dimensão | Modelo default | Fallback |
|---|---|---|
| `factuality` | `openai/gpt-4o-mini` | `anthropic/claude-3-5-haiku` |
| `relevance` | `openai/gpt-4o-mini` | — |
| `harmfulness` | `openai/gpt-4o` | — (safety crítica) |
| `coherence` | `openai/gpt-4o-mini` | — |
| `completeness` | `openai/gpt-4o-mini` | — |

## Worker (Argo Workflows)

```yaml
# workflows/judge.yaml (resumo)
apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata:
  name: judge-run
spec:
  entrypoint: judge
  templates:
    - name: judge
      steps:
        - - name: check-cache
            template: cache-lookup
        - - name: call-judges
            template: parallel-judges
            when: "{{steps.check-cache.outputs.parameters.hit}} == false"
        - - name: persist
            template: persist-result
```

## Telemetria do próprio agent

| Métrica | Tipo | Labels |
|---|---|---|
| `judge_jobs_total` | counter | `org_id`, `dimension` |
| `judge_job_duration_seconds` | histogram | `dimension` |
| `judge_cache_hit_total` | counter | `dimension` |
| `judge_cache_miss_total` | counter | `dimension` |
| `judge_disagreement_total` | counter | `dimension` |
| `judge_cost_usd_total` | counter | `model` |

## Onde mora

```
services/judge/
├── app/
│   ├── main.py
│   ├── enqueue.py
│   ├── cache.py
│   ├── runner.py
│   ├── compare.py
│   └── prompts/
│       ├── factuality.v1.txt
│       ├── relevance.v1.txt
│       └── ...
├── workflows/
│   └── judge.yaml
├── tests/
└── Dockerfile
```

## Dependências externas

- Postgres (events, judge_results)
- Redis (cache)
- S3 (artifacts)
- OpenAI / Anthropic APIs
- Argo Workflows (orchestrator)

## Out of scope

- Definir SLO de judge → `12-infra.md`
- Renderizar scores na UI → `10-ui.md`
- Auto-trigger baseado em heurística → PRD §5.5; vive em `ingest-agent` que enfileira
