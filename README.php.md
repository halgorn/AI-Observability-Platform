# AI Observability Platform — PHP

Cliente mínimo para enviar eventos de agentes de IA para o AI Observability Platform.
Funciona com **zero pacotes Composer** — usa `ext-curl` e `ext-json` (habilitadas por padrão).

## Pré-requisitos

| Item | Versão mínima |
|---|---|
| PHP | 8.1 (readonly properties + `match`) |
| Extensões | `ext-curl`, `ext-json` (built-in em qualquer instalação padrão) |
| Composer | não necessário |

## Configuração

Adicione ao seu `.env` ou passe via variável de ambiente:

```env
AI_OBS_INGEST_URL=https://SEU-DOMINIO.COM
AI_OBS_SERVICE_TOKEN=ai_obs_v1.<token-com-scope-ingest.write>
```

> O token é gerado via `POST /v1/tokens` no ingest-api ou com
> `AiObs::issueToken()` (apenas para testes locais).

## Instalação

Copie `examples/php/ai_obs.php` para o seu projeto:

```bash
curl -O https://raw.githubusercontent.com/<seu-repo>/main/examples/php/ai_obs.php
# ou copie manualmente de examples/php/ai_obs.php
```

## Uso

### Configurar uma vez no boot

```php
require_once __DIR__ . '/ai_obs.php';

AiObs::configure(
    ingestUrl: $_ENV['AI_OBS_INGEST_URL'],
    token:     $_ENV['AI_OBS_SERVICE_TOKEN']
);
```

### Run + observe

```php
AiObs::run('meu-agente', ['query' => 'Olá'], function (RunContext $ctx) {
    // emite llm.call automaticamente
    $resposta = AiObs::observe(llm: 'openai/gpt-4o-mini', fn: function () {
        $client = new \GuzzleHttp\Client(); // ou qualquer HTTP client
        return $client->post('https://api.openai.com/v1/chat/completions', [...])->getBody();
    });

    // emite tool.invoke
    $dados = AiObs::observe(tool: 'buscar-dados', fn: fn() => DB::select('SELECT 1'));

    // checkpoint e handoff
    $ctx->checkpoint(step: 1, state: ['resposta' => $resposta]);
    $ctx->handoff(to: 'agente-revisor', reason: 'delegation', payload: ['dados' => $dados]);
});
```

### Em um framework (Laravel, Symfony, etc.)

```php
// Coloque o configure() no AppServiceProvider::boot() ou equivalente.
// O AiObs é uma classe estática pura — funciona em qualquer contexto PHP.

class MeuController
{
    public function processar(Request $request)
    {
        return AiObs::run('api-agente', $request->all(), function (RunContext $ctx) use ($request) {
            $resultado = AiObs::observe(llm: 'openai/gpt-4o-mini', fn: function () use ($request) {
                return $this->openai->chamar($request->input('query'));
            });
            return response()->json(['resultado' => $resultado]);
        });
    }
}
```

### Gerar token (só para testes locais)

```php
$token = AiObs::issueToken(
    secret: $_ENV['INGEST_API_SECRET'],
    orgId:  'minha-org',
    scopes: ['ingest.write']
);
```

## Referência de eventos

Envelope (campos obrigatórios em **negrito**):

| Campo | Tipo | Notas |
|---|---|---|
| **`run_id`** | UUID string | identificador do run |
| **`span_id`** | 16 hex chars | identificador do span |
| **`type`** | string | ver tabela abaixo |
| **`started_at`** | ISO 8601 | ex: `2026-06-30T12:00:00+00:00` |
| **`payload`** | array/object | campos variam por tipo |
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

Se o seu projeto já usa [opentelemetry-php](https://github.com/open-telemetry/opentelemetry-php),
aponte o exporter para `/v1/traces`:

```bash
composer require open-telemetry/exporter-otlp
```

```php
$exporter = new \OpenTelemetry\Contrib\Otlp\OtlpHttpExporter(
    (new \OpenTelemetry\SDK\Common\Export\Http\PsrTransportFactory())->create(
        $_ENV['AI_OBS_INGEST_URL'] . '/v1/traces',
        'application/json',
        ['Authorization' => 'Bearer ' . $_ENV['AI_OBS_SERVICE_TOKEN']]
    )
);
```

O ingest-api converte automaticamente os spans OTLP para eventos nativos.

## Verificação

1. Suba o stack local:
   ```bash
   docker compose up -d
   ```
2. Rode o teste:
   ```bash
   php -r "
   require 'ai_obs.php';
   AiObs::configure(getenv('AI_OBS_INGEST_URL'), getenv('AI_OBS_SERVICE_TOKEN'));
   AiObs::run('teste-php', ['ok' => true], function (\$ctx) {
     AiObs::observe(llm: 'openai/gpt-4o-mini', fn: fn() => usleep(100000));
     \$ctx->checkpoint(1, ['done' => true]);
   });
   echo 'Enviado!' . PHP_EOL;
   "
   ```
3. Acesse **http://localhost:3000/runs** — o run `teste-php` deve aparecer.
4. Confirme nos logs:
   ```bash
   docker compose logs ingest-api --tail=20
   # procure: "accepted":1
   ```
