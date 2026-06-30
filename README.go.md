# AI Observability Platform — Go

Cliente mínimo para enviar eventos de agentes de IA para o AI Observability Platform.
Funciona com **zero dependências externas** — só a stdlib do Go.

## Pré-requisitos

| Item | Versão mínima |
|---|---|
| Go | 1.21 |
| Módulos externos | nenhum |

## Configuração

Exporte as variáveis de ambiente (ou use uma lib como `godotenv`):

```env
AI_OBS_INGEST_URL=https://SEU-DOMINIO.COM
AI_OBS_SERVICE_TOKEN=ai_obs_v1.<token-com-scope-ingest.write>
```

> O token é gerado via `POST /v1/tokens` no ingest-api ou com a função
> `IssueToken` (apenas para testes locais).

## Instalação

Copie `examples/go/ai_obs.go` para o seu módulo Go:

```bash
# copie o arquivo para o package do seu projeto
cp examples/go/ai_obs.go seu-projeto/internal/aiobs/ai_obs.go

# ajuste o package name se necessário
# package aiobs → package seupackage
```

Nenhum `go get` necessário.

## Uso

### Configurar uma vez no boot

```go
import "seu-projeto/internal/aiobs"

func main() {
    aiobs.Configure(
        os.Getenv("AI_OBS_INGEST_URL"),
        os.Getenv("AI_OBS_SERVICE_TOKEN"),
    )
    // ...
}
```

### Run + Observe

```go
err := aiobs.Run("meu-agente", map[string]any{"query": "Olá"}, func(ctx *aiobs.RunContext) error {
    // emite llm.call automaticamente
    result, err := aiobs.Observe("openai/gpt-4o-mini", "", "", func() (any, error) {
        return openaiClient.CreateChatCompletion(context.Background(), openai.ChatCompletionRequest{
            Model:    "gpt-4o-mini",
            Messages: []openai.ChatCompletionMessage{{Role: "user", Content: "Olá"}},
        })
    })
    if err != nil {
        return err
    }

    // emite tool.invoke
    _, _ = aiobs.Observe("", "buscar-dados", "", func() (any, error) {
        return db.QueryContext(context.Background(), "SELECT 1")
    })

    // checkpoint e handoff
    ctx.Checkpoint(1, map[string]any{"result": result})
    ctx.Handoff("agente-revisor", "delegation", map[string]any{"result": result})

    return nil
})
```

> `Observe(llm, tool, agentName, fn)` — passe uma string não-vazia apenas no
> campo correspondente ao tipo de evento (`llm`, `tool`, ou `agentName`).

### Gerar token (só para testes locais)

```go
token := aiobs.IssueToken(
    os.Getenv("INGEST_API_SECRET"),
    "minha-org",
    "default",
    []string{"ingest.write"},
    365*24*3600,
)
```

### UUID v4 externo (opcional)

Para produção com melhor randomness, substitua `mustUUID()` por
[`github.com/google/uuid`](https://pkg.go.dev/github.com/google/uuid):

```go
// go get github.com/google/uuid
import "github.com/google/uuid"
// troque mustUUID() por uuid.New().String()
```

## Referência de eventos

Envelope (campos obrigatórios em **negrito**):

| Campo | Tipo | Notas |
|---|---|---|
| **`run_id`** | UUID string | identificador do run |
| **`span_id`** | 16 hex chars | identificador do span |
| **`type`** | string | ver tabela abaixo |
| **`started_at`** | RFC 3339 | ex: `2026-06-30T12:00:00Z` |
| **`payload`** | objeto JSON | campos variam por tipo |
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

Se o seu projeto já usa [go.opentelemetry.io/otel](https://pkg.go.dev/go.opentelemetry.io/otel),
aponte o exporter para `/v1/traces`:

```bash
go get go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp
```

```go
exporter, _ := otlptracehttp.New(ctx,
    otlptracehttp.WithEndpoint(os.Getenv("AI_OBS_INGEST_URL")),
    otlptracehttp.WithURLPath("/v1/traces"),
    otlptracehttp.WithHeaders(map[string]string{
        "Authorization": "Bearer " + os.Getenv("AI_OBS_SERVICE_TOKEN"),
    }),
)
```

O ingest-api converte automaticamente os spans OTLP para eventos nativos.

## Verificação

1. Suba o stack local:
   ```bash
   docker compose up -d
   ```
2. Rode o teste:
   ```go
   // test/main.go
   package main

   import (
       "fmt"
       "os"
       aiobs "seu-projeto/internal/aiobs"
   )

   func main() {
       aiobs.Configure(os.Getenv("AI_OBS_INGEST_URL"), os.Getenv("AI_OBS_SERVICE_TOKEN"))
       aiobs.Run("teste-go", map[string]any{"ok": true}, func(ctx *aiobs.RunContext) error {
           aiobs.Observe("openai/gpt-4o-mini", "", "", func() (any, error) {
               return nil, nil // simula chamada LLM
           })
           ctx.Checkpoint(1, map[string]any{"done": true})
           return nil
       })
       fmt.Println("Enviado!")
   }
   ```
   ```bash
   go run test/main.go
   ```
3. Acesse **http://localhost:3000/runs** — o run `teste-go` deve aparecer.
4. Confirme nos logs:
   ```bash
   docker compose logs ingest-api --tail=20
   # procure: "accepted":1
   ```
