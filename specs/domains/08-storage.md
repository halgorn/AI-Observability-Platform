# 08 — Storage Domain

4 storages, **1 por perfil de acesso**.

| Store | Tipo | Usado por | Retention |
|---|---|---|---|
| Postgres 16 | relacional, transacional | `events` (truth), `checkpoints`, `judge_results`, `runs` | 30 dias hot |
| ClickHouse Cloud | colunar, analítico | agregações de cost/token/latency | 1 ano |
| Redis (Upstash) | KV + cache | judge cache, replay sessions, rate limit | TTL-based |
| S3 / disk | blob | artifacts (raw LLM I/O, prompts, embeddings) | indefinido (cold) |
| Tempo | trace store | UI de trace estilo Jaeger | 30 dias |
| pgvector | vector | similarity search de runs (embeddings de input) | 30 dias hot |

## Postgres — schema completo

```sql
-- Runs (1 linha por run, atualizada em run.end)
CREATE TABLE runs (
    run_id          UUID PRIMARY KEY,
    thread_id       TEXT,
    agent           TEXT NOT NULL,
    status          TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    duration_ms     INT,
    total_steps     INT,
    total_tokens    INT,
    total_cost_usd  NUMERIC(12,8),
    input_hash      TEXT,
    output_hash     TEXT,
    prompt_version  TEXT,
    parent_run_id   UUID,
    tags            JSONB DEFAULT '{}'::jsonb,
    org_id          TEXT NOT NULL,           -- Clerk org
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_runs_org_started  ON runs(org_id, started_at DESC);
CREATE INDEX idx_runs_status       ON runs(status) WHERE status IN ('failed','timeout');
CREATE INDEX idx_runs_agent        ON runs(agent, started_at DESC);

-- Events (já em 02-event-schema.md)

-- Checkpoints (já em 05-replay.md)

-- Judge results (já em 07-judge.md)

-- Artifacts
CREATE TABLE artifacts (
    id           BIGSERIAL PRIMARY KEY,
    type         TEXT NOT NULL,   -- 'prompt' | 'agent_code' | 'embedding' | 'tool_io'
    hash         TEXT NOT NULL UNIQUE,
    version      TEXT,
    content      BYTEA,           -- null se external (s3_uri presente)
    s3_uri       TEXT,
    size_bytes   INT NOT NULL,
    content_type TEXT,
    metadata     JSONB DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Org (denormalizado p/ multi-tenant; Clerk é source of truth)
CREATE TABLE orgs (
    org_id   TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    plan     TEXT NOT NULL DEFAULT 'free',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## ClickHouse — modelo

```sql
CREATE TABLE events_ch (
    started_at   DateTime64(9),
    run_id       UUID,
    span_id      FixedString(16),
    parent_span_id Nullable(FixedString(16)),
    type         LowCardinality(String),
    agent        LowCardinality(String),
    tool         LowCardinality(String),
    llm_model    LowCardinality(String),
    duration_ms  UInt32,
    tokens_in    UInt32,
    tokens_out   UInt32,
    cost_usd     Float64,
    error_code   LowCardinality(String),
    attributes   String CODEC(ZSTD(3))
) ENGINE = MergeTree
  PARTITION BY toYYYYMM(started_at)
  ORDER BY (run_id, started_at, span_id)
  TTL started_at + INTERVAL 1 YEAR;
```

Mirror populado por **Kafka consumer** (Redpanda → ClickHouse). Não é fonte de verdade.

## Redis — keys canônicas

```
judge:cache:{model}:{sha256}            → JSON JudgeResult, TTL 30d
replay:session:{session_id}             → JSON ReplaySession, TTL 1h
replay:step:{run_id}:{step}             → bytes state, TTL 24h
ratelimit:ingest:{org_id}:{minute}      → int, TTL 60s
ratelimit:replay:{org_id}               → int, TTL 1s
lock:replay:{run_id}                    → "1", TTL 1h
feature:{flag}                          → bool/int/json, TTL infinito
```

## S3 — layout

```
s3://ai-obs-artifacts/
  org={org_id}/
    run={run_id}/
      step={step}/
        llm_input.json     ← só metadados + hash; raw em llm_raw
        llm_output.json
        tool_io.json
        embedding.parquet
    prompt={prompt_version}/
      content.txt
      hash.sha256
    agent={agent_name}/
      code.zip
      hash.sha256
```

- SSE-S3 encryption habilitada.
- Lifecycle: hot 30d → IA 90d → Glacier 1y → delete.
- Acesso: signed URL TTL 5 min (NUNCA URL pública).

## pgvector — embeddings

```sql
CREATE TABLE run_embeddings (
    run_id    UUID NOT NULL,
    input     TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL,   -- ada-002 / text-embedding-3-small
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id)
);

CREATE INDEX idx_run_embeddings_vec ON run_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

- Embedding gerado **on-demand** em `POST /runs/{id}/similar`.
- Custo: ~$0.00002/1k tokens.
- v2: migrar para **Qdrant** se cardinalidade > 10M runs.

## Sizing — metas (PRD §6)

| Métrica | Meta |
|---|---|
| Storage de 1 run (média) | < 50 KB metadata + artifacts |
| Throughput ingest | 1000 spans/s sustentado |
| Query `/trace` p95 | < 300 ms (run ≤ 500 spans) |
| Retention hot | 30 dias |
| Retention cold | 1 ano |

## Backup e DR

| Store | Estratégia | RPO | RTO |
|---|---|---|---|
| Postgres | PITR + daily snapshot S3 | 5 min | 1 h |
| ClickHouse | replicação 3x + backup diário | 1 h | 4 h |
| Redis | efêmero, reconstruível | n/a | n/a |
| S3 | versioning + cross-region | 0 | 0 |
| Tempo | WAL → S3 | 1 h | 4 h |

## O que este domínio **NÃO** decide

- Como cada storage é provisionado → `12-infra.md`
- Quem lê o quê → `11-auth.md`
