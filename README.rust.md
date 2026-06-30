# AI Observability Platform — Rust

Cliente mínimo para enviar eventos de agentes de IA para o AI Observability Platform.
Rust não tem HTTP/JSON na stdlib, então usa um conjunto pequeno de crates bem estabelecidas.

## Pré-requisitos

| Item | Versão mínima |
|---|---|
| Rust | 1.75 (stable) |
| Cargo | qualquer versão compatível |

### Dependências (`Cargo.toml`)

```toml
[dependencies]
reqwest   = { version = "0.12", features = ["blocking", "json"] }
serde     = { version = "1",    features = ["derive"] }
serde_json = "1"
hmac      = "0.12"
sha2      = "0.10"
base64    = "0.22"
uuid      = { version = "1", features = ["v4"] }
chrono    = "0.4"
```

> `reqwest` com `blocking` evita a necessidade de um runtime tokio para uso simples.
> Para projetos async (tokio/actix), remova `blocking` e use `.await` normalmente.

## Configuração

Exporte as variáveis de ambiente no seu projeto:

```env
AI_OBS_INGEST_URL=https://SEU-DOMINIO.COM
AI_OBS_SERVICE_TOKEN=ai_obs_v1.<token-com-scope-ingest.write>
```

> O token é gerado via `POST /v1/tokens` no ingest-api ou com a função
> `issue_token` (apenas para testes locais).

## Instalação

Copie `examples/rust/src/lib.rs` para o seu projeto e adicione as deps ao `Cargo.toml`:

```bash
# copie lib.rs para seu módulo
cp examples/rust/src/lib.rs src/ai_obs.rs
# ajuste `mod ai_obs;` no main.rs/lib.rs do seu projeto
```

Depois instale as deps:

```bash
cargo build
```

## Uso

### Configurar uma vez no boot

```rust
mod ai_obs; // ou: use seu_crate::ai_obs;

fn main() {
    ai_obs::configure(
        std::env::var("AI_OBS_INGEST_URL").unwrap(),
        std::env::var("AI_OBS_SERVICE_TOKEN").unwrap(),
    );
    // ...
}
```

### Run + observe

```rust
use serde_json::json;

ai_obs::run("meu-agente", &json!({ "query": "Olá" }), |ctx| {
    // emite llm.call automaticamente
    let resposta = ai_obs::observe("openai/gpt-4o-mini", "", "", || {
        // sua chamada real aqui
        openai_client.chat("gpt-4o-mini", "Olá")
    });

    // emite tool.invoke
    let dados = ai_obs::observe("", "buscar-dados", "", || {
        db.query("SELECT 1")
    });

    // checkpoint e handoff
    ctx.checkpoint(1, &json!({ "resposta": resposta }));
    ctx.handoff("agente-revisor", "delegation", &json!({ "dados": dados }));

    Ok(())
})?;
```

> `observe(llm, tool, agent_name, fn)` — passe uma string não-vazia apenas no
> campo correspondente ao tipo de evento.

### Uso async (tokio)

Para projetos com `tokio`, adicione `reqwest` sem o feature `blocking` e
substitua as chamadas HTTP por async:

```toml
reqwest = { version = "0.12", features = ["json"] }
tokio   = { version = "1",    features = ["full"] }
```

Extraia a função `emit` para async e use `tokio::spawn` para fire-and-forget.

### Gerar token (só para testes locais)

```rust
let token = ai_obs::issue_token(
    &std::env::var("INGEST_API_SECRET").unwrap(),
    "minha-org",
    "default",
    &["ingest.write"],
    365 * 24 * 3600,
);
```

## Referência de eventos

Envelope (campos obrigatórios em **negrito**):

| Campo | Tipo | Notas |
|---|---|---|
| **`run_id`** | UUID string | identificador do run |
| **`span_id`** | 16 hex chars | identificador do span |
| **`type`** | string | ver tabela abaixo |
| **`started_at`** | RFC 3339 | ex: `2026-06-30T12:00:00+00:00` |
| **`payload`** | JSON object | campos variam por tipo |
| `parent_span_id` | 16 hex chars | span pai (opcional) |
| `ended_at` | RFC 3339 | opcional |
| `agent`, `llm_model`, `tool` | string | metadados extras |

Tipos de evento e payload obrigatório:

| `type` | Payload obrigatório |
|---|---|
| `run.start` | `agent`, `input_hash` |
| `run.end` | `status` (succeeded/failed/timeout/cancelled) |
| `step.start` | `step` (int ≥ 0) |
| `step.end` | `step`, `status` |
| `llm.call` | `model` (formato `provider/model-name`) |
| `tool.invoke` | `tool`, `args_hash` (sha256:…) |
| `handoff` | `from`, `to`, `reason` |
| `checkpoint` | `step`, `state_hash` (sha256:…) |
| `error` | `code` (enum — ver `specs/schemas/event-types.v1.json`) |
| `judge.result` | `model`, `dimension`, `score` (0.0–1.0) |
| `artifact.link` | `artifact_hash`, `kind` |

Schema completo: [`specs/schemas/event.v1.json`](specs/schemas/event.v1.json) e
[`specs/schemas/event-types.v1.json`](specs/schemas/event-types.v1.json).

## Alternativa: OpenTelemetry

Se o seu projeto já usa [opentelemetry-rust](https://github.com/open-telemetry/opentelemetry-rust),
aponte o exporter para `/v1/traces`:

```toml
opentelemetry      = "0.24"
opentelemetry-otlp = { version = "0.17", features = ["http-proto"] }
```

```rust
let exporter = opentelemetry_otlp::new_exporter()
    .http()
    .with_endpoint(format!("{}/v1/traces", std::env::var("AI_OBS_INGEST_URL").unwrap()))
    .with_headers(std::collections::HashMap::from([(
        "Authorization".into(),
        format!("Bearer {}", std::env::var("AI_OBS_SERVICE_TOKEN").unwrap()),
    )]));
```

O ingest-api converte automaticamente os spans OTLP para eventos nativos.

## Verificação

1. Suba o stack local:
   ```bash
   docker compose up -d
   ```
2. Crie um binário de teste `examples/rust/src/main.rs`:
   ```rust
   use ai_obs as aiobs;
   use serde_json::json;

   fn main() {
       aiobs::configure(
           std::env::var("AI_OBS_INGEST_URL").unwrap(),
           std::env::var("AI_OBS_SERVICE_TOKEN").unwrap(),
       );
       aiobs::run("teste-rust", &json!({ "ok": true }), |ctx| {
           aiobs::observe("openai/gpt-4o-mini", "", "", || {
               std::thread::sleep(std::time::Duration::from_millis(100));
           });
           ctx.checkpoint(1, &json!({ "done": true }));
           Ok::<(), ()>(())
       }).unwrap();
       println!("Enviado!");
   }
   ```
   ```bash
   cd examples/rust
   cargo run
   ```
3. Acesse **http://localhost:3000/runs** — o run `teste-rust` deve aparecer.
4. Confirme nos logs:
   ```bash
   docker compose logs ingest-api --tail=20
   # procure: "accepted":1
   ```
