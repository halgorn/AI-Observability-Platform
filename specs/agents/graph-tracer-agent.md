# Agent Card — `graph-tracer-agent`

**Responsabilidade:** SDK Python que instrumenta LangGraph com zero-touch, emite eventos canônicos.

## Domínios lidos

| Domínio | Lê? |
|---|---|
| `00-glossary.md` | ✅ |
| `01-naming-conventions.md` | ✅ |
| `02-event-schema.md` | ✅ (gera `Event` instances) |
| `03-tracing.md` | ✅ (autoridade — este agent **é** o SDK descrito lá) |
| `04-agent-orchestration.md` | ✅ (mapeia callbacks LangGraph → eventos) |
| `06-cost.md` | ✅ (calcula `cost_usd` em `llm.call`) |
| `08-storage.md` | ✅ (não escreve direto, mas sabe shape dos eventos) |
| `14-data-governance.md` | ✅ (PII redaction **antes** de emitir) |
| `15-conformance.md` | ✅ (contract tests) |

## Domínios proibidos

- `05-replay.md` — não decide replay
- `07-judge.md` — judge é consumer
- `09-api.md`, `10-ui.md`, `11-auth.md` — não toca API/UI/auth
- `12-infra.md` — não decide deploy do SDK
- `13-sandbox.md` — não roda em sandbox

## Contratos de entrada

| Input | Tipo | Validação |
|---|---|---|
| `langgraph.PostgresSaver` | instance | duck-typed (tem `put`, `get`) |
| `langgraph.CompiledGraph` | instance | duck-typed (tem `invoke`, `stream`) |
| Configuração | `TracerConfig` | Pydantic v2 |

```python
class TracerConfig(BaseModel):
    agent_name: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    org_id: str
    sample_rate: float = Field(ge=0, le=1, default=0.1)
    redact_keys: list[str] = ["password", "api_key", "token", "ssn", "email"]
    mock_on_error: bool = False
```

## Contratos de saída

| Output | Tipo | Destino |
|---|---|---|
| Spans | OTLP genai.* | OTel Collector (via OTLP exporter) |
| Eventos | `Event` (Pydantic) | OTel Collector (custom exporter paralelo) |
| Métricas locais | `tracer.*` (Prometheus) | /metrics endpoint |

## Invariantes

1. **Decorator nunca swallow exception** — sempre re-raise após emitir `error` event.
2. **`run_id` propagado por `contextvars`** — imutável dentro de uma run.
3. **`parent_span_id` derivado de contexto OTel** — nunca setado manualmente.
4. **`cost_usd` calculado no `llm.call` end** — não no start; usa `pricing_for(model, ts)`.
5. **Sampling decision recorded como `sampling.decision` attribute** — não como header.
6. **PII redacted antes de emitir** — match por `redact_keys` em `attributes` e `payload`.
7. **`__replay__` prefix em agent name durante replay** — `ReplayEngine` é quem seta.
8. **Backward-compat com OTel semconv 0.3 e 0.4** — detectado em runtime, ambos suportados.

## Hooks LangGraph

| LangGraph callback | Evento ai-obs |
|---|---|
| `on_chain_start` | `step.start` |
| `on_chain_end` | `step.end` |
| `on_chain_error` | `error` |
| `on_tool_start` | `tool.invoke` start |
| `on_tool_end` | `tool.invoke` end |
| `on_llm_start` | `llm.call` start |
| `on_llm_end` | `llm.call` end |
| custom `on_handoff` | `handoff` |
| `PostgresSaver.put` | `checkpoint` (event-only; state vai no saver) |

## Telemetria do próprio agent

| Métrica | Tipo |
|---|---|
| `tracer_spans_emitted_total` | counter |
| `tracer_overhead_ms` | histogram |
| `tracer_sampling_decisions_total` | counter `{decision}` |
| `tracer_pii_redactions_total` | counter |
| `tracer_emit_errors_total` | counter `{error_code}` |

## Onde mora

```
packages/ai-obs-sdk/
├── src/ai_obs/
│   ├── __init__.py            # public: observe, run, handoff, trace_context
│   ├── tracer.py
│   ├── decorators.py
│   ├── langgraph/
│   │   ├── graph_tracer.py
│   │   ├── callbacks.py
│   │   └── checkpoint_hook.py
│   ├── pricing.py
│   ├── redact.py
│   └── schemas.py             # Pydantic v2
├── tests/
└── pyproject.toml
```

## Distribuição

- **PyPI:** `ai-obs-sdk`
- Versão sincronizada com spec (ex.: `ai-obs-sdk==0.4.2` ↔ `02-event-schema.md` v1).
- Compat matrix: Python ≥ 3.10, LangGraph ≥ 0.2.

## Out of scope

- Implementar judge, replay engine, UI — vive em outros agents.
- Modificar Postgres schema — só emite eventos no shape definido.
