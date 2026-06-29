# 02 — Event Schema

**A** verdade do sistema é a tabela `events`. Tudo deriva dela.

## Modelo lógico

```
events (append-only)
   │
   ├── in: OTel SDK, GraphTracer, manual emit
   ├── out: ClickHouse (agregado), Query API, Judge, Replay
   └── constraint: PK = (id), UNIQUE = (run_id, span_id)
```

## Tabela canônica (Postgres)

```sql
CREATE TABLE events (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID         NOT NULL,
    parent_span_id  BYTEA        NULL,    -- 8 bytes
    span_id         BYTEA        NOT NULL, -- 8 bytes
    type            TEXT         NOT NULL,
    agent           TEXT         NULL,
    tool            TEXT         NULL,
    llm_model       TEXT         NULL,
    started_at      TIMESTAMPTZ  NOT NULL,
    ended_at        TIMESTAMPTZ  NULL,
    duration_ms     INT          NULL,
    tokens_in       INT          NULL,
    tokens_out      INT          NULL,
    cost_usd        NUMERIC(12,8) NULL,
    error_code      TEXT         NULL,
    payload         JSONB        NOT NULL,
    attributes      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT chk_event_ended CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX idx_events_run_id_started ON events(run_id, started_at);
CREATE INDEX idx_events_type_started   ON events(type, started_at);
CREATE INDEX idx_events_agent_started  ON events(agent, started_at) WHERE agent IS NOT NULL;
```

> Versão inicial. Mudanças incompatíveis (remover coluna, mudar tipo) = `event.v2` + migration.

## Shape JSON (canônico em `schemas/event.v1.json`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ai-obs.local/schemas/event.v1.json",
  "title": "RunEvent",
  "type": "object",
  "required": ["run_id", "span_id", "type", "started_at", "payload"],
  "additionalProperties": false,
  "properties": {
    "run_id":         { "type": "string", "format": "uuid" },
    "parent_span_id": { "type": ["string", "null"], "pattern": "^[0-9a-f]{16}$" },
    "span_id":        { "type": "string", "pattern": "^[0-9a-f]{16}$" },
    "type":           { "$ref": "#/$defs/EventType" },
    "agent":          { "type": ["string", "null"], "pattern": "^[a-z0-9_-]{1,64}$" },
    "tool":           { "type": ["string", "null"], "pattern": "^[a-z0-9_.-]{1,64}$" },
    "llm_model":      { "type": ["string", "null"] },
    "started_at":     { "type": "string", "format": "date-time" },
    "ended_at":       { "type": ["string", "null"], "format": "date-time" },
    "duration_ms":    { "type": ["integer", "null"], "minimum": 0 },
    "tokens_in":      { "type": ["integer", "null"], "minimum": 0 },
    "tokens_out":     { "type": ["integer", "null"], "minimum": 0 },
    "cost_usd":       { "type": ["number", "null"], "minimum": 0 },
    "error_code":     { "$ref": "#/$defs/ErrorCode" },
    "payload":        { "type": "object" },
    "attributes":     { "type": "object", "additionalProperties": true }
  },
  "$defs": {
    "EventType": {
      "enum": [
        "llm.call","tool.invoke","handoff","checkpoint",
        "error","judge.result","run.start","run.end",
        "step.start","step.end","artifact.link"
      ]
    },
    "ErrorCode": {
      "enum": [
        "LLM_TIMEOUT","LLM_RATE_LIMIT","LLM_INVALID_OUTPUT",
        "TOOL_TIMEOUT","TOOL_NOT_FOUND","TOOL_INVALID_ARGS",
        "HANDOFF_REJECTED","CHECKPOINT_MISSING","REPLAY_DIVERGED",
        "JUDGE_DISAGREEMENT","INGEST_REJECTED","AUTH_MISSING",
        "AUTH_FORBIDDEN","BUDGET_EXCEEDED","UNKNOWN"
      ]
    }
  }
}
```

## Payload por tipo (sub-shape)

Cada `type` exige um sub-shape em `payload`. Validação é feita no **ingest**, não no reader.

> Sub-shapes formais em `schemas/event-types.v1.json` (discriminator via `oneOf`). Validador Pydantic v2 usa isso como modelo.

### `run.start`

```json
{
  "input_hash":   "sha256:...",
  "input_size":   1234,
  "agent":        "planner",
  "thread_id":    "thr_abc",
  "prompt_version": "v3.1.0"
}
```

### `run.end`

```json
{
  "status":       "succeeded|failed|timeout|cancelled",
  "output_hash":  "sha256:...",
  "output_size":  5678,
  "total_steps":  12,
  "total_tokens": 4521,
  "total_cost_usd": 0.002341
}
```

### `llm.call`

```json
{
  "model":          "openai/gpt-4o-mini",
  "messages_hash":  "sha256:...",
  "messages_size":  8421,
  "finish_reason":  "stop|length|tool_calls|content_filter",
  "system_prompt_version": "v3.1.0"
}
```

> Conteúdo de `messages` **não** vai no payload do evento. Vai em `artifacts` (S3) com link em `attributes.artifact_ref`.

### `tool.invoke`

```json
{
  "args_hash":     "sha256:...",
  "result_hash":   "sha256:...",
  "result_size":   2048,
  "cache_hit":     false,
  "retry_count":   0
}
```

### `handoff`

```json
{
  "from":     "planner",
  "to":       "executor",
  "payload_hash": "sha256:...",
  "reason":   "delegation|escalation|fallback"
}
```

### `checkpoint`

```json
{
  "step":    7,
  "state_hash": "sha256:...",
  "state_size":  3412
}
```

> State completo **não** vai no evento. Vai na tabela `checkpoints` (FK `run_id`).

### `error`

```json
{
  "code":    "TOOL_TIMEOUT",
  "message": "browser_fetch exceeded 30s budget",
  "retryable": true,
  "stack":   "optional, redacted"
}
```

### `judge.result`

```json
{
  "model":      "openai/gpt-4o-mini",
  "dimension":  "factuality|relevance|harmfulness|coherence",
  "score":      0.0,
  "rationale":  "string",
  "cache_hit":  true
}
```

## Regras invariantes

1. **Eventos são imutáveis.** Nada faz UPDATE no `payload`.
2. **Todo span terminal emite 2 eventos:** `step.start` e `step.end` (ou `error`).
3. **`run_id` é gerado uma vez por run** — propagado por `traceparent` OTel.
4. **Sem `payload` vazio.** Mínimo: `{}` é proibido; precisa ter **algum** fato.
5. **`cost_usd` é populated se e só se houve LLM call real.**
6. **Ordenação canônica:** `(run_id, started_at, span_id)` — nunca confiar só em `id`.
7. **Validação em camadas:**
   - envelope: `schemas/event.v1.json`
   - `payload` por `type`: `schemas/event-types.v1.json`
   - `attributes`: `schemas/attributes.v1.json` (whitelist + extension)
8. **Adulteração de schema = breaking change.** Regras em `15-conformance.md` §Versionamento.

## Ingest contract

`POST /v1/events` aceita:

- OTLP gRPC (path `/opentelemetry.proto.collector.trace.v1.TraceService/Export`)
- OTLP HTTP (path `/v1/traces`)
- REST JSON (path `/v1/events`, body = array de `Event`)

Validação Pydantic v2 → JSON Schema acima. **Falha de validação = `INGEST_REJECTED` com `error.code` + DLQ em Redpanda.**

## ClickHouse mirror

Mesma linha, formato `Native`, engine `MergeTree`, partition by `toYYYYMM(started_at)`, order by `(run_id, started_at)`. Sem JSONB — colunas tipadas por `type` via `LowCardinality(String)`.
