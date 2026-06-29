# 14 — Data Governance

PII, retention, LGPD/GDPR, data residency, lineage, direito ao esquecimento.

> **Premissa:** payload de evento pode conter PII do usuário final. Tratamos PII como **veneno** — opt-in, não opt-out.

## Categorias de dado

| Categoria | Exemplos | Cuidado |
|---|---|---|
| **Identificador** | `run_id`, `span_id`, `org_id` | OK, não é PII |
| **Metadata** | `agent`, `tool`, `llm_model`, timestamps | OK |
| **Conteúdo redacted** | `input_hash`, `output_hash` (hashes) | OK; hash é one-way |
| **Conteúdo raw opt-in** | `input_ref`, `messages_ref` em S3 | **PII potencial**; precisa `pii=true` flag |
| **Prompt** | texto de system/user prompt | Pode ter PII do dev |
| **Tool I/O** | args e result de tool | **Maior risco** (ex.: `db_query("SELECT * FROM users")`) |
| **Embedding** | vetor de input | Pode vazar informação se invertido |

## Política de PII

### Defaults (opt-out)

| Lugar | Comportamento default |
|---|---|
| `events.payload` | **sem** raw text — só hashes e refs |
| `attributes` | só whitelist de `attributes.v1.json` |
| `artifacts` (S3) | **não** ingere; opt-in explícito |
| `judge_results.rationale` | texto livre, mas passa por PII scan |

### PII detection (3 camadas)

1. **Regex blocklist** (rápido, comum):
   - email, CPF, CNPJ, phone (BR/US), credit card (Luhn), SSN, IP público
2. **ML classifier** (médio, fallback):
   - modelo `pii-distilbert` (Hugging Face) ou similar
   - threshold: `score > 0.85` = PII
3. **Deny-list de keys em payload** (estrutural):
   - `password`, `api_key`, `token`, `secret`, `ssn`, `cpf`, `cnpj`, `credit_card`, `email`, `phone`

### Redaction

```python
REDACTION_RULES = [
    (r"\b[\w.-]+@[\w.-]+\.\w+\b", "[REDACTED:email]"),
    (r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "[REDACTED:cpf]"),
    (r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b", "[REDACTED:card]"),
    # ... full list em config/pii-rules.yaml
]
```

- Redacted no **SDK antes de emitir** (latência zero no ingest).
- Substituição é **case-preserving** e **length-preserving** quando possível.
- Hash do valor original é mantido em `attributes.pii.original_hash` para auditoria.

### Modos

| Mode | Quando | Comportamento |
|---|---|---|
| `strict` | default para `plan=free` | PII detectado = `INGEST_REJECTED` + DLQ |
| `redact` | default para `plan=pro` | PII detectado = redaction automática + evento aceito |
| `passthrough` | opt-in para `plan=enterprise` | PII permitido (BAA assinado); alerta mas não rejeita |

## Retention

| Store | Hot | Cold | Delete |
|---|---|---|---|
| Postgres `events` | 30 dias | n/a | 30 dias |
| Postgres `checkpoints` | 30 dias | n/a | 30 dias (estado raw) |
| Postgres `runs` | 1 ano | n/a | 1 ano |
| ClickHouse `events_ch` | 1 ano | n/a | 1 ano |
| Redis | TTL-based | n/a | TTL |
| S3 `artifacts` | 30 dias (hot) | 1 ano (Glacier) | 1 ano |
| Tempo | 30 dias | n/a | 30 dias |
| `judge_results` | 1 ano | n/a | 1 ano |
| `audit_log` | 1 ano | n/a | 1 ano |
| `service_tokens` | enquanto ativo | n/a | 90 dias após revoke |

### Janela deslizante

- Hot → cold: job noturno (Argo Cron) move dados > 30d para S3 Glacier.
- Delete: job noturno apaga dados > retention.
- Org pode **encurtar** retention por config (`max_retention_days`), nunca estender além do cap.

## Data residency

| Região | Stores | Compliance |
|---|---|---|
| `us-east-1` | tudo | SOC2, GDPR via SCC |
| `eu-west-1` | tudo | GDPR nativo |
| `sa-east-1` | tudo | LGPD nativo |

- Replay **só** roda em sandbox na mesma região do run original.
- Cross-region export só via API explícita do admin (auditado).
- Org `plan=enterprise` pode pin de região.

## Direito ao esquecimento (LGPD art. 18)

### Fluxo

```
User/Admin → POST /v1/orgs/{id}/gdpr/erase
  body: { scope: "all" | "user:{user_id}" | "run:{run_id}" }

→ Job assíncrono (Argo)
  1. Marca runs como `gdpr.erased = true`
  2. Apaga events, checkpoints, judge_results
  3. Apaga artifacts S3
  4. Mantém aggregates anonimizados em CH (ex.: "agent X, count Y")
  5. Gera certificate of erasure, envia p/ admin
  6. Audit log entry
```

### Slug de anonimização

```sql
-- Run apagado vira "ghost"
UPDATE runs SET 
    input_hash = 'sha256:0000000000000000000000000000000000000000000000000000000000000000',
    output_hash = 'sha256:000000...',
    tags = '{"gdpr_erased": true}'::jsonb
WHERE run_id = $1;
-- events/checkpoints/judge_results: DELETE
-- artifacts S3: DELETE
```

- Aggregates ClickHouse **retidos** mas sem possibilidade de join com `run_id`.
- Erased runs ainda contam em métricas agregadas (count, p95) mas não são acessíveis por API.
- Certificate: PDF gerado com timestamp, lista de IDs apagados, hash da operação.

## Data export (LGPD art. 18 V)

```
GET /v1/orgs/{id}/gdpr/export
  query: { since, until, format: "json" | "parquet" }

→ Job assíncrono → signed URL S3 (TTL 7 dias)
  - Inclui runs, events, judge_results, prompts do user
  - NÃO inclui dados de outros orgs
  - Não inclui aggregates
```

## Data lineage

```sql
CREATE TABLE lineage (
    from_kind    TEXT,    -- 'input' | 'llm_io' | 'tool_io' | 'judge'
    from_hash    TEXT,
    to_kind      TEXT,
    to_hash      TEXT,
    run_id       UUID,
    span_id      BYTEA,
    step         INT,
    created_at   TIMESTAMPTZ,
    PRIMARY KEY (from_kind, from_hash, to_kind, to_hash)
);
```

- Permite responder: "todos os outputs derivados do input `sha256:abc`"
- Usado em: investigations de bug, A/B diff de prompt, recall de runs afetados.

## Audit log

```sql
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    org_id      TEXT NOT NULL,
    actor_id    TEXT NOT NULL,
    actor_type  TEXT NOT NULL,           -- 'user' | 'service_token' | 'system'
    action      TEXT NOT NULL,           -- 'gdpr.erase', 'slo.update', 'run.replay', 'judge.enqueue', ...
    target      TEXT,
    metadata    JSONB DEFAULT '{}'::jsonb,
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- Ações cobertas: tudo em `11-auth.md` + `gdpr.erase` + `gdpr.export` + `slo.update` + `service_token.create/revoke`.
- Retenção: 1 ano.
- Acesso: `owner`/`admin` only.
- Imutável (append-only, RLS desabilita DELETE).

## Erros

| Cenário | `error.code` |
|---|---|
| PII em modo strict | `PII_DETECTED` |
| Erasure em progresso | `GDPR_ERASURE_PENDING` |
| Erasure falhou | `GDPR_ERASURE_FAILED` |
| Export sem permissão | `GDPR_EXPORT_FORBIDDEN` |

## O que este domínio **NÃO** decide

- Onde PII é detectado pelo SDK → `03-tracing.md` (chama regras daqui)
- Como UI mostra badge de "PII redacted" → `10-ui.md`
- Quem tem permissão de erasure → `11-auth.md` (admin only)
