# 03 — Tracing Domain

Tudo que envolve **emitir, rotear e armazenar telemetria**.

## Stack

| Camada | Ferramenta | Spec autoritativa |
|---|---|---|
| SDK cliente | `ai-obs-sdk` (PyPI) | este doc + `04-agent-orchestration.md` |
| Collector | OpenTelemetry Collector | OTel upstream |
| Receiver | `IngestAPI` (FastAPI) | `09-api.md` |
| Buffer | Redpanda (Kafka) | `08-storage.md` |
| Storage quente | Postgres + ClickHouse | `08-storage.md` |
| Storage trace UI | Grafana Tempo | `08-storage.md` |

## SDK Python — superfície pública

```python
from ai_obs import observe, run, handoff, trace_context

# 1. Decorator genérico
@observe(agent="planner")
def think(state: State) -> State: ...

@observe(tool="browser.fetch")
def fetch(url: str) -> str: ...

@observe(llm="openai/gpt-4o-mini")
async def llm_call(prompt: str) -> str: ...

# 2. Context manager
with run(agent="orchestrator", input=req) as r:
    r.handoff(to="executor", payload=plan)
    result = await executor.run(plan)

# 3. Tracing context (propagação)
ctx = trace_context(traceparent=req.headers["traceparent"])
```

## Regras do decorator `@observe`

1. `agent`, `tool`, `llm` são **mutuamente exclusivos** — exatamente 1 obrigatório.
2. Decorator **sempre** emite 2 eventos: `step.start` e `step.end` (ou `error`).
3. Nome do span = `<key>.<value>` (ex.: `agent.planner`, `tool.browser.fetch`).
4. Exceção não-tratada vira `error` event com `error.code = UNKNOWN` (caller pode sobrescrever).
5. Exceção é **re-raise** após emissão — decorator não swallow.
6. Async-safe: usa `contextvars` para propagar `trace_id`/`span_id`.

## Atributos semânticos `genai.*`

Tabela de mapping SDK → span attribute:

| Decorator / API | Attribute | Exemplo |
|---|---|---|
| `@observe(agent=...)` | `genai.agent.name` | `planner` |
| `@observe(tool=...)` | `genai.tool.name` | `browser.fetch` |
| `@observe(llm=...)` | `genai.llm.model` | `openai/gpt-4o-mini` |
| `llm_call` response | `genai.llm.tokens.input` | `342` |
| `llm_call` response | `genai.llm.tokens.output` | `128` |
| `llm_call` response | `genai.llm.cost.usd` | `0.000234` |
| `handoff()` | `genai.handoff.from` / `.to` | `planner` → `executor` |
| `run()` | `genai.run.id` | UUID v7 |
| Qualquer span | `genai.prompt.version` | `v3.1.0` |

> Versão do schema semântico: **fixar `opentelemetry-semantic-conventions-genai == 0.4.x`** (ver risco R-3 do PRD).

## Sampling

```yaml
# config padrão (overridable por agent)
default:
  errors:   1.0   # 100% dos erros
  success:  0.1   # 10% dos sucessos
  judge_trigger: ["error", "succeeded_with_low_score"]
  budget_per_run: 5000   # max events/run, hard cap
```

- Sampling decidido **no SDK** (head-based) + ajustado no **collector** (tail-based).
- Toda decisão de sample **vira atributo** `sampling.decision` no span.
- Run com **qualquer erro** é always-on.

## Overhead budget

| Métrica | Meta | Medição |
|---|---|---|
| Latência adicional por span | < 1ms p50, < 5ms p99 | benchmark `bench/spans.py` |
| Memória adicional por run | < 2 MB | profiler contínuo |
| Bytes adicionais por run | < 50 KB metadata | soma `payload` + `attributes` |

> Se overhead > meta, **reduzir sampling de success**, nunca cortar atributos canônicos.

## Collector — pipeline mínimo

```yaml
receivers:
  otlp:
    protocols: { grpc: {}, http: {} }

processors:
  batch:        { send_batch_size: 1024, timeout: 200ms }
  memory_limiter: { check_interval: 100ms, limit_mib: 1024 }
  tail_sampler: { decision_wait: 10s, num_traces: 100000 }
  attributes/genai: { actions: [{key: "genai.*", action: insert}] }

exporters:
  otlphttp/ingest: { endpoint: "http://ingest-api:8000" }
  otlphttp/tempo:  { endpoint: "http://tempo:4318" }
  prometheus:      { endpoint: ":8889" }

service:
  pipelines:
    traces:  [otlp, memory_limiter, tail_sampler, batch, otlphttp/ingest, otlphttp/tempo]
    metrics: [otlp, batch, prometheus]
```

## Erros canônicos do tracing

| Cenário | `error.code` | Recovery |
|---|---|---|
| OTLP endpoint unreachable | `INGEST_REJECTED` | retry exp backoff no SDK |
| Schema inválido | `INGEST_REJECTED` | DLQ → alerta |
| Trace id duplicado | (descartar silencioso) | idempotência por `(run_id, span_id)` |
| Budget excedido | `BUDGET_EXCEEDED` | sample agressivo, span continua parcial |

## O que este domínio **NÃO** decide

- Como calcular `cost_usd` → `06-cost.md`
- Como re-executar → `05-replay.md`
- Como julgar qualidade → `07-judge.md`
- Onde armazenar state completo → `08-storage.md`
- Como UI renderiza → `10-ui.md`
