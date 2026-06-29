# Agent Card — `ingest-agent`

**Responsabilidade:** receber telemetria (OTLP/REST), validar, persistir, rotear.

## Domínios lidos (autoridade)

| Domínio | Lê? | Motivo |
|---|---|---|
| `00-glossary.md` | ✅ | vocabulário |
| `01-naming-conventions.md` | ✅ | nomes de campo, enums |
| `02-event-schema.md` | ✅ | contrato de evento |
| `03-tracing.md` | ✅ | atributos semânticos, sampling |
| `08-storage.md` | ✅ | shape Postgres + ClickHouse mirror |
| `09-api.md` | ✅ | endpoints ingest, rate limits |
| `11-auth.md` | ✅ | service tokens |
| `12-infra.md` | ✅ | deploy, autoscaling |
| `14-data-governance.md` | ✅ | PII detection, retention, rejection |
| `15-conformance.md` | ✅ | contract tests, schema validation |

## Domínios proibidos (NÃO lê/NÃO decide)

- `04-agent-orchestration.md` — não interpreta handoffs
- `05-replay.md` — replay é cliente, não ingest
- `07-judge.md` — judge lê eventos, não produz
- `10-ui.md` — não toca em UI
- `13-sandbox.md` — sandbox é de replay, não de ingest

## Contratos de entrada

| Origem | Schema | Validação |
|---|---|---|
| OTLP gRPC | `schemas/span.v1.json` (OTLP genai.*) | Pydantic v2 |
| OTLP HTTP | mesmo | Pydantic v2 |
| REST `POST /v1/events` | `schemas/event.v1.json` | Pydantic v2 + JSON Schema |

## Contratos de saída

| Destino | Schema | Garantia |
|---|---|---|
| Postgres `events` | linha append-only | at-least-once + idempotência por `(run_id, span_id)` |
| Redpanda `events.raw` | bytes (JSON) | exatamente o que chegou, para replay e ClickHouse mirror |
| ClickHouse (via consumer) | schema `events_ch` | eventual consistency (≤ 30s) |
| Tempo | OTLP trace | sem transformação |
| DLQ (Redpanda `events.dlq`) | `{event, error}` | em caso de `INGEST_REJECTED` |

## Invariantes (nunca viola)

1. **Idempotência por `(run_id, span_id)`** — segundo insert com mesma chave = no-op silencioso.
2. **Falha de validação = `INGEST_REJECTED` + DLQ** — nunca descartar sem rastro.
3. **Latência adicional no hot path < 1ms p50** — pré-validação em buffer, validação pesada assíncrona.
4. **Sampling é decidido no SDK, não no ingest** — ingest aceita o que recebe; collector tail-sample é config.
5. **Nada de PII no payload de evento** — opt-in redaction antes de aceitar; payload com PII = `INGEST_REJECTED` se flag `redact_strict=true`.
6. **Tamanho máximo payload: 5 MB por evento, 50 MB por request batch** — além disso = `INGEST_REJECTED`.
7. **Org isolation no insert** — `org_id` vem do service token, nunca do body.

## Telemetria esperada (do próprio agent)

| Métrica | Tipo | Labels |
|---|---|---|
| `ingest_events_total` | counter | `org_id`, `type`, `status` |
| `ingest_rejected_total` | counter | `org_id`, `error_code` |
| `ingest_latency_seconds` | histogram | `endpoint` |
| `ingest_payload_bytes` | histogram | `type` |
| `ingest_dlq_size` | gauge | — |
| `ingest_clickhouse_lag_seconds` | gauge | — |

Span attributes em **toda request**:
- `http.method`, `http.route`, `http.status_code`
- `ingest.org_id`
- `ingest.event_count`
- `ingest.rejected_count`

## Onde mora (paths)

```
services/ingest-api/
├── app/
│   ├── main.py
│   ├── otlp_receiver.py
│   ├── rest_receiver.py
│   ├── validator.py
│   ├── pipeline.py
│   └── auth.py
├── tests/
└── Dockerfile
```

## Dependências externas

- Postgres (`POSTGRES_DSN`)
- Redpanda (`KAFKA_BROKERS`)
- OTel Collector (upstream)
- Tempo (downstream, OTLP HTTP)

## Out of scope

- Construir OTLP collector (usamos upstream).
- Decidir modelo de pricing (lê `06-cost.md`).
- Renderizar UI de erro (responde JSON).
