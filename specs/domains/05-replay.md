# 05 — Replay Domain

Re-executar uma run **bit-a-bit** a partir de checkpoints.

## Garantia

> Replay é determinístico no caminho de **tools e handoffs**. No caminho de **LLM**, é determinístico apenas quando o LLM está **mockado** (mesmo `seed`, mesma `model`, cache de judge por hash).

## Fluxo

```
┌─────────┐  GET /runs/{id}/replay   ┌──────────┐
│   UI    │ ───────────────────────▶ │  Replay  │
└─────────┘                          │  Engine  │
     ▲                                └────┬─────┘
     │ state diff, stepper                 │
     │                                     ▼
     │                              ┌──────────────┐
     │                              │  Postgres    │
     │                              │  + Redis     │
     │                              │  + S3        │
     │                              └──────────────┘
     │
     │ Run com status=replaying
     ▼
┌──────────────────────────┐
│ Sandbox executor         │
│ - tools mockáveis        │
│ - LLM mockável (opcional)│
│ - mesmo seed de random   │
└──────────────────────────┘
```

## ReplayEngine — contrato

```python
class ReplayEngine:
    async def load(self, run_id: UUID) -> ReplaySession: ...
    async def step(self, session: ReplaySession, n: int) -> ReplayStep: ...
    async def toggle_mock(self, session: ReplaySession, target: MockTarget) -> None: ...
    async def reset_to(self, session: ReplaySession, step: int) -> None: ...
    async def replay_full(self, session: ReplaySession) -> ReplayResult: ...
```

## ReplaySession — shape

```python
@dataclass
class ReplaySession:
    session_id: UUID
    run_id: UUID
    total_steps: int
    current_step: int
    mock_llm: bool
    mock_tools: set[str]      # tool names mocked
    seed: int                 # RNG seed, default = sha256(run_id)[:8]
    diverged_at: int | None   # primeiro step onde divergiu, ou None
    status: Literal["ready","replaying","done","diverged"]
```

## Determinismo — fontes de não-determinismo controladas

| Fonte | Solução |
|---|---|
| LLM temperature > 0 | `mock_llm=True` + cache por `(input_hash, model)` |
| Tool side-effects (POST) | tool é mockada se marcada como side-effect |
| Wall clock | substituído por `started_at` do checkpoint |
| UUID v4 | substituído por `uuid5(NAMESPACE, run_id)` |
| Random | `random.seed(session.seed)` |
| Network | `httpx.MockTransport` registrado no sandbox |

## Divergência

```python
def check_divergence(replayed: Step, original: Step) -> bool:
    return (
        replayed.tool != original.tool
        or replayed.tool_args_hash != original.tool_args_hash
        or (replay_llm and replayed.llm_output_hash != original.llm_output_hash)
    )
```

- 1ª divergência grava `events.type = error, error.code = REPLAY_DIVERGED`.
- Continua replay para mostrar **o que mudou**, não aborta.
- UI marca divergência em vermelho; permite avançar/retomar.

## Checkpoint shape (tabela)

```sql
CREATE TABLE checkpoints (
    run_id     UUID        NOT NULL,
    step       INT         NOT NULL,
    state      JSONB       NOT NULL,
    state_hash TEXT        NOT NULL,
    thread_id  TEXT        NOT NULL,
    saved_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, step),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX idx_checkpoints_thread ON checkpoints(thread_id, saved_at);
```

## Cache layer

```python
# Redis keys
replay:session:{session_id}      → JSON ReplaySession (TTL 1h)
replay:step:{run_id}:{step}      → bytes state (TTL 24h, hit em ~30% dos replays)
artifact:by_hash:{hash}          → S3 ref (TTL 7d, link estável)
```

## Artefato de replay

Cada replay emite um **novo** `run` com:

- `parent_run_id` = `run_id` original
- `status = replaying` durante, `succeeded` ao final
- tag `replay_of={run_id}` em `attributes`
- **Não** emite eventos para `cost_usd` (LLM é mockado)
- **Não** conta em métricas de produção

## Limites v1

| Limite | Valor |
|---|---|
| Max steps por replay | 500 |
| Max tamanho de state | 5 MB |
| Janela de retenção para replay | 30 dias (hot), 1 ano (cold/S3) |
| Replays simultâneos por run | 1 (lock) |
| Replays simultâneos por org | 10 |

## O que este domínio **NÃO** decide

- Quem autoriza o replay → `11-auth.md`
- Como UI stepper renderiza → `10-ui.md`
- Como custo é computado em prod → `06-cost.md`
