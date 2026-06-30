# AI Observability Platform — Node.js

Cliente mínimo para enviar eventos de agentes de IA para o AI Observability Platform.
Funciona com **zero dependências npm** — usa `fetch` e `crypto` nativos do Node 18+.

## Pré-requisitos

| Item | Versão mínima |
|---|---|
| Node.js | 18 LTS (fetch nativo + `crypto.randomUUID`) |
| npm packages | nenhum |

## Configuração

Crie um `.env` (ou use `process.env`) no seu projeto:

```env
AI_OBS_INGEST_URL=https://SEU-DOMINIO.COM
AI_OBS_SERVICE_TOKEN=ai_obs_v1.<token-com-scope-ingest.write>
```

> O token é gerado via `POST /v1/tokens` no ingest-api ou com a função
> `issueToken` (apenas para testes locais).

## Instalação

Copie `examples/nodejs/ai_obs.js` para o seu projeto:

```bash
curl -O https://raw.githubusercontent.com/<seu-repo>/main/examples/nodejs/ai_obs.js
# ou copie manualmente de examples/nodejs/ai_obs.js
```

Nenhum `npm install` necessário.

## Uso

### Configurar uma vez no boot

```js
const aiObs = require('./ai_obs');

aiObs.configure({
  ingestUrl: process.env.AI_OBS_INGEST_URL,
  token:     process.env.AI_OBS_SERVICE_TOKEN,
});
```

### Run + observe

```js
const { configure, run, observe } = require('./ai_obs');

configure({ ingestUrl: process.env.AI_OBS_INGEST_URL, token: process.env.AI_OBS_SERVICE_TOKEN });

await run('meu-agente', { query: 'Olá' }, async (ctx) => {
  // emite llm.call automaticamente
  const resposta = await observe({ llm: 'openai/gpt-4o-mini' }, async () => {
    const res = await openai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: 'Olá' }],
    });
    return res.choices[0].message.content;
  });

  // emite tool.invoke
  const dados = await observe({ tool: 'buscar-dados' }, () => db.query('SELECT 1'));

  // checkpoint e handoff
  ctx.checkpoint(1, { resposta });
  ctx.handoff('agente-revisor', 'delegation', { dados });
});
```

### TypeScript (sem @types necessário)

```ts
import { configure, run, observe, RunContext } from './ai_obs';

// O módulo funciona diretamente com ts-node ou compilado.
// Para tipagem completa, declare o módulo em um arquivo .d.ts local se necessário.
```

### Gerar token (só para testes locais)

```js
const { issueToken } = require('./ai_obs');
const token = issueToken(process.env.INGEST_API_SECRET, {
  orgId: 'minha-org',
  scopes: ['ingest.write'],
});
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

Se o seu projeto já usa [@opentelemetry/sdk-node](https://www.npmjs.com/package/@opentelemetry/sdk-node),
aponte o exporter para `/v1/traces`:

```js
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http');

const exporter = new OTLPTraceExporter({
  url: `${process.env.AI_OBS_INGEST_URL}/v1/traces`,
  headers: { Authorization: `Bearer ${process.env.AI_OBS_SERVICE_TOKEN}` },
});
```

O ingest-api converte automaticamente os spans OTLP para eventos nativos.

## Verificação

1. Suba o stack local:
   ```bash
   docker compose up -d
   ```
2. Rode o teste:
   ```js
   // test_ai_obs.js
   const { configure, run, observe } = require('./ai_obs');
   configure({ ingestUrl: process.env.AI_OBS_INGEST_URL, token: process.env.AI_OBS_SERVICE_TOKEN });

   (async () => {
     await run('teste-node', { ok: true }, async (ctx) => {
       await observe({ llm: 'openai/gpt-4o-mini' }, async () => {
         await new Promise(r => setTimeout(r, 100));
       });
       ctx.checkpoint(1, { done: true });
     });
     console.log('Enviado!');
   })();
   ```
   ```bash
   node test_ai_obs.js
   ```
3. Acesse **http://localhost:3000/runs** — o run `teste-node` deve aparecer.
4. Confirme nos logs:
   ```bash
   docker compose logs ingest-api --tail=20
   # procure: "accepted":1
   ```
