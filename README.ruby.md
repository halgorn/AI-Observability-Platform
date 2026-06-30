# AI Observability Platform — Ruby

Cliente mínimo para enviar eventos de agentes de IA para o AI Observability Platform.
Funciona com **zero gems externas** — só a stdlib do Ruby.

## Pré-requisitos

| Item | Versão mínima |
|---|---|
| Ruby | 2.7 (keyword args) |
| Gems | nenhuma — `net/http`, `json`, `securerandom`, `digest`, `openssl`, `time` são stdlib |

## Configuração

Crie um `.env` (ou exporte as variáveis) no seu projeto Ruby:

```env
AI_OBS_INGEST_URL=https://SEU-DOMINIO.COM
AI_OBS_SERVICE_TOKEN=ai_obs_v1.<token-com-scope-ingest.write>
```

> O token é gerado via `POST /v1/tokens` no ingest-api ou com a função
> `AiObs.issue_token` (apenas para testes locais).

## Instalação

Copie `examples/ruby/ai_obs.rb` para o seu projeto:

```bash
curl -O https://raw.githubusercontent.com/<seu-repo>/main/examples/ruby/ai_obs.rb
# ou copie manualmente de examples/ruby/ai_obs.rb
```

Não há `bundle install` — nenhuma gem é necessária.

## Uso

### Configurar uma vez no boot

```ruby
require_relative 'ai_obs'

AiObs.configure(
  ingest_url: ENV.fetch('AI_OBS_INGEST_URL'),
  token:      ENV.fetch('AI_OBS_SERVICE_TOKEN')
)
```

### Run + observe (estilo bloco)

```ruby
AiObs.run(agent: 'meu-agente', input: { query: 'Olá' }) do |ctx|
  # emite llm.call automaticamente
  resposta = AiObs.observe(llm: 'openai/gpt-4o-mini') do
    client.chat(model: 'gpt-4o-mini', messages: [{ role: 'user', content: 'Olá' }])
  end

  # emite tool.invoke
  dados = AiObs.observe(tool: 'buscar-dados') { db.query('SELECT 1') }

  # salvar checkpoint
  ctx.checkpoint(step: 1, state: { resposta: resposta })

  # handoff para outro agente
  ctx.handoff(to: 'agente-revisor', reason: 'delegation', payload: { dados: dados })
end
```

### Decorator em métodos de classe

```ruby
class MeuAgente
  extend AiObs::Decorator

  def chamar_llm(prompt)
    # sua chamada real aqui
  end
  observe :chamar_llm, llm: 'openai/gpt-4o-mini'

  def buscar(query)
    # sua busca aqui
  end
  observe :buscar, tool: 'buscar'
end
```

### Gerar token (só para testes locais)

```ruby
token = AiObs.issue_token(
  secret: ENV.fetch('INGEST_API_SECRET'),
  org_id: 'minha-org',
  scopes: ['ingest.write']
)
```

## Referência de eventos

Envelope (campos obrigatórios em **negrito**):

| Campo | Tipo | Notas |
|---|---|---|
| **`run_id`** | UUID string | identificador do run |
| **`span_id`** | 16 hex chars | identificador do span |
| **`type`** | string | ver tabela abaixo |
| **`started_at`** | ISO 8601 | ex: `2026-06-30T12:00:00Z` |
| **`payload`** | object | campos variam por tipo |
| `parent_span_id` | 16 hex chars | span pai (opcional) |
| `ended_at` | ISO 8601 | opcional |
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

Se o seu projeto já usa o [OpenTelemetry Ruby SDK](https://opentelemetry.io/docs/languages/ruby/),
você pode apontar o OTLP HTTP exporter direto para `/v1/traces`:

```ruby
# gem 'opentelemetry-exporter-otlp'
OpenTelemetry::SDK.configure do |c|
  c.add_span_processor(
    OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor.new(
      OpenTelemetry::Exporter::OTLP::Exporter.new(
        endpoint: "#{ENV['AI_OBS_INGEST_URL']}/v1/traces",
        headers: { 'Authorization' => "Bearer #{ENV['AI_OBS_SERVICE_TOKEN']}" }
      )
    )
  )
end
```

O ingest-api converte automaticamente os spans OTLP para eventos nativos.

## Verificação

1. Suba o stack local:
   ```bash
   docker compose up -d
   ```
2. Rode o script de teste:
   ```bash
   ruby -e "
   require_relative 'ai_obs'
   AiObs.configure(ingest_url: ENV['AI_OBS_INGEST_URL'], token: ENV['AI_OBS_SERVICE_TOKEN'])
   AiObs.run(agent: 'teste-ruby', input: { ok: true }) do |ctx|
     AiObs.observe(llm: 'openai/gpt-4o-mini') { sleep 0.1 }
     ctx.checkpoint(step: 1, state: { done: true })
   end
   puts 'Enviado!'
   "
   ```
3. Acesse **http://localhost:3000/runs** — o run `teste-ruby` deve aparecer.
4. Confirme nos logs:
   ```bash
   docker compose logs ingest-api --tail=20
   # procure: "accepted":1
   ```
