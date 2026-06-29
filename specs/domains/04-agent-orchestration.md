# 04 — Agent Orchestration Domain

Como modelamos **agentes, handoffs e state machines**.

## Conceito

Agente = unidade de raciocínio. Handoff = delegação explícita. State machine = estrutura que governa transições.

> A observability captura a **máquina**, não só as chamadas externas.

## Tipos canônicos

```python
class Agent:
    name: str            # ex: "planner"
    role: Literal[
        "planner",      # decompõe problema
        "executor",     # executa tool calls
        "reviewer",     # avalia output
        "critic",       # avalia processo
        "router",       # decide handoff
        "synthesizer",  # combina outputs parciais
    ]
    prompt_version: str  # semver, FK p/ artifacts
    tools: list[str]
    parent: str | None   # multi-agent squad
```

## Handoff — modelo de grafo

```python
handoff(
    from_agent: str,
    to_agent: str,
    payload: Any,        # serializável
    reason: Literal["delegation","escalation","fallback","retry"],
)
```

- Handoff **sempre** emite `events.type = handoff`.
- Payload completo vai em artifact; evento carrega `payload_hash`.
- Aresta do grafo é `(from, to)`; `reason` é atributo de styling na UI.
- Self-handoff (A→A) só permitido com `reason = retry`.

## Grafo de handoff

Estrutura derivada de eventos (`type = handoff`):

```sql
CREATE MATERIALIZED VIEW handoff_graph AS
SELECT
    from_agent,
    to_agent,
    count(*) FILTER (WHERE error_code IS NULL) AS success_count,
    count(*) AS total_count,
    count(*) FILTER (WHERE error_code IS NULL)::float / nullif(count(*), 0) AS success_rate
FROM events
WHERE type = 'handoff'
  AND started_at > now() - interval '7 days'
GROUP BY from_agent, to_agent;
```

View materializada refreshed a cada 5 min (ou on-demand em click).

## LangGraph drop-in

`GraphTracer` é o adapter. **Não** substitui o `PostgresSaver` — só escuta.

```python
from langgraph.checkpoint.postgres import PostgresSaver
from ai_obs.langgraph import GraphTracer

saver = PostgresSaver.from_conn_string(POSTGRES_DSN)
tracer = GraphTracer(
    saver=saver,
    agent_name="planner",
    run_id=run_id,
    sample_rate=0.1,
)

graph = builder.compile(checkpointer=saver, callbacks=[tracer])
```

### Hooks do `GraphTracer`

| Evento LangGraph | Evento `ai-obs` |
|---|---|
| `on_chain_start` | `step.start` |
| `on_chain_end` | `step.end` (success) |
| `on_chain_error` | `error` |
| `on_tool_start` | `tool.invoke` (start) |
| `on_tool_end` | `tool.invoke` (end) |
| `on_llm_start` | `llm.call` (start) |
| `on_llm_end` | `llm.call` (end) |
| `on_handoff` (custom) | `handoff` |
| `PostgresSaver.put` | `checkpoint` |

## State machine — invariantes

1. **Step counter é monotonic** por run: `0, 1, 2, ..., n`.
2. **Checkpoint por step**: `(run_id, step)` é PK; `step` é exclusivo.
3. **State hash versionado**: `state_hash = sha256(canonical_json(state))` — canonicalização usa `json.dumps(..., sort_keys=True)`.
4. **Branching** (parallel nodes) gera múltiplos eventos com mesmo `step`, distinguidos por `parent_span_id`.
5. **Re-entry** (loop) é permitida; `step` cresce.

## Multi-agent squad

```
            ┌──────────────┐
            │  orchestrator│
            └──────┬───────┘
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   ┌────────┐  ┌────────┐  ┌────────┐
   │planner │  │executor│  │reviewer│
   └────┬───┘  └───┬────┘  └────┬───┘
        └────┬─────┘            │
             ▼                  │
        ┌─────────┐             │
        │  critic │◀────────────┘
        └─────────┘
```

- Squad = conjunto de agentes coordenados.
- Squad tem `orchestrator` (router ou fixed).
- `parent_run_id` no evento = id da run pai quando este agente foi invocado por outro.

## Nomes reservados

| Nome | Uso |
|---|---|
| `__system__` | spans internos do SDK (health, startup) |
| `__replay__` | spans durante replay (não contam em prod metrics) |
| `__judge__` | spans do JudgeService (não contam em cost de usuário) |

## Erros de orquestração

| Cenário | `error.code` | Impacto |
|---|---|---|
| Tool inexistente | `TOOL_NOT_FOUND` | step falho, handoff de fallback |
| Args inválidos | `TOOL_INVALID_ARGS` | step falho, retry 1x, depois `error` |
| Handoff recusado pelo target | `HANDOFF_REJECTED` | router decide próximo |
| Loop infinito detectado | (custom `BUDGET_EXCEEDED`) | run cancelada |
| Checkpoint ausente (replay) | `CHECKPOINT_MISSING` | replay abortado |

## O que este domínio **NÃO** decide

- Como LLM é chamado → integração fica no decorator, pricing fica em `06-cost.md`
- Como replay usa estes dados → `05-replay.md`
- Como UI desenha o grafo → `10-ui.md`
