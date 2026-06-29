# Agent Card — `replay-agent`

**Responsabilidade:** re-executar runs **bit-a-bit** a partir de checkpoints.

## Domínios lidos

| Domínio | Lê? |
|---|---|
| `00-glossary.md` | ✅ |
| `01-naming-conventions.md` | ✅ |
| `02-event-schema.md` | ✅ |
| `04-agent-orchestration.md` | ✅ (state machine semantics) |
| `05-replay.md` | ✅ (autoridade — implementa o que está aqui) |
| `08-storage.md` | ✅ (checkpoints table, S3 artifacts, Redis keys) |
| `09-api.md` | ✅ (endpoint `GET /v1/runs/{id}/replay`) |
| `11-auth.md` | ✅ (scope `runs.replay`) |
| `13-sandbox.md` | ✅ (autoridade — orquestra sandbox) |
| `14-data-governance.md` | ✅ (data residency, PII em artifact) |
| `15-conformance.md` | ✅ (contract tests) |

## Domínios proibidos

- `03-tracing.md` — emite spans com prefixo `__replay__`; não decide OTel pipeline
- `06-cost.md` — replay **não** computa cost (LLM mockado)
- `07-judge.md` — judge pode rodar **sobre** replay, mas este agent não invoca
- `10-ui.md` — não renderiza; só serve dados para o stepper
- `12-infra.md` — não decide deploy

## Contratos de entrada

| Input | Fonte | Validação |
|---|---|---|
| `run_id` | API request | UUID v7, exists in `runs` |
| `ReplayConfig` | API request body | Pydantic v2 |
| Checkpoints | Postgres `checkpoints` | shape `ReplayStep` |
| Artifacts | S3 (via `artifacts.s3_uri`) | sha256 verified |

```python
class ReplayConfig(BaseModel):
    mock_llm: bool = True
    mock_tools: set[str] = Field(default_factory=set)
    seed: int | None = None       # default = sha256(run_id)[:8]
    start_step: int = 0
    end_step: int | None = None   # default = total_steps
```

## Contratos de saída

| Output | Destino | Schema |
|---|---|---|
| `ReplaySession` | Redis (TTL 1h) | Pydantic v2 |
| `ReplayStep` per request | API response | Pydantic v2 |
| `events.type = run.start` com `parent_run_id` | OTel collector | mesmo shape de run normal |
| Divergence event | OTel collector | `error.code = REPLAY_DIVERGED` |
| Spans com `genai.replay.*` attrs | OTel collector | prefixo `__replay__` em `agent` |

## Invariantes

1. **Determinismo onde der** — RNG seedado, wall clock substituído, UUIDs derivados.
2. **Divergência não aborta** — registra e continua, mostrando diff.
3. **Lock por run** — 1 replay simultâneo por `run_id` (Redis `lock:replay:{run_id}`, TTL 1h).
4. **Limite de steps** — 500 hard cap, 5MB max state, 30 dias retenção.
5. **LLM mock sempre default** — `mock_llm=True` por segurança.
6. **Tool mock opt-in explícito** — `mock_tools` é set explícito; tool side-effect nunca roda sem mock.
7. **Custo zero** — replay **nunca** emite `cost_usd > 0`.
8. **Org isolation** — replay só do mesmo `org_id` da run original.
9. **Audit log entry** — `action = run.replay` com `actor_id`, `run_id`, `config`.

## API exposta

```
GET  /v1/runs/{id}/replay              → { url, session_id, total_steps }
POST /v1/replay/{session_id}/step      → { step: ReplayStep }
POST /v1/replay/{session_id}/reset     → { step: int } → { step: ReplayStep }
POST /v1/replay/{session_id}/toggle    → { target: 'llm' | 'tool', value: bool | str }
POST /v1/replay/{session_id}/run       → { job_id }
GET  /v1/replay/{session_id}/status    → { status, current_step, diverged_at }
```

## Telemetria do próprio agent

| Métrica | Tipo | Labels |
|---|---|---|
| `replay_sessions_total` | counter | `org_id` |
| `replay_session_duration_seconds` | histogram | — |
| `replay_divergences_total` | counter | `org_id`, `step_bucket` |
| `replay_step_latency_ms` | histogram | — |
| `replay_active_sessions` | gauge | `org_id` |

## Onde mora

```
services/replay-engine/
├── app/
│   ├── main.py
│   ├── session.py
│   ├── sandbox.py
│   ├── divergence.py
│   ├── lock.py
│   └── auth.py
├── tests/
└── Dockerfile
```

## Dependências externas

- Postgres (checkpoints + runs)
- Redis (sessions, locks, step cache)
- S3 (artifacts)
- Sandbox executor (subprocess ou worker isolado)

## Out of scope

- Decidir visualização do stepper → `10-ui.md`
- Calcular judge score sobre replay → `07-judge.md` (roda depois, se invocado)
- Adicionar features de produção (alerts, SLO) → `12-infra.md`
