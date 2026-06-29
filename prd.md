# PRD — AI Observability Platform

**Status:** Draft v0.1
**Owner:** Bruno
**Target level:** Staff / Principal

## 0. Stack (mercado)

| Camada | Ferramenta | Por quê |
|---|---|---|
| Tracing | **OpenTelemetry** + **Tempo** (Grafana) | Padrão aberto; não amarra a vendor |
| LLM proxy / cost | **Helicone** (referência) + próprio | Aprendemos o shape de proxy HTTP-based |
| Replay / state | **LangGraph `PostgresSaver`** + **Langfuse** (refs) | Checkpoint nativo; Langfuse como espelho OSS |
| Storage relacional | **Postgres 16** + **pgvector** | Events + embeddings no mesmo banco |
| Storage colunar | **ClickHouse Cloud** | Agregações em bilhões de spans |
| Métricas / SLO | **Prometheus** + **Grafana Cloud** | Padrão SRE; alerting maduro |
| Cache de replay | **Redis** (Upstash) | Checkpoint cache + dedupe de judge |
| Backend | **FastAPI** + **Pydantic v2** | Async nativo, type safety |
| Streaming ingest | **Redpanda** (Kafka-compat) | Buffer durável antes do ClickHouse |
| Background jobs | **Argo Workflows** ou **Temporal** | Judge async + replay batch |
| Auth | **Clerk** | Login + orgs/teams em 1 dia |
| Frontend | **Next.js 14** (App Router) + **shadcn/ui** + **Tailwind** | Velocidade + estética |
| Visualização de grafo | **React Flow** | Handoff graph interativo |
| Visualização de trace | **react-querybuilder** + custom tree | Estilo Jaeger |
| Deploy backend | **Fly.io** | Máquinas em múltiplas regiões, low-friction |
| Deploy frontend | **Vercel** | DX padrão de mercado |
| CI/CD | **GitHub Actions** | Padrão |
| Observability do próprio produto | **Sentry** + **Highlight.io** | Dogfooding interno |
| LLM judge | **GPT-4o-mini** + cache por hash | Custo-controlado |
| Vector search | **pgvector** (v1) → **Qdrant** (v2 se crescer) | Um banco a menos pra operar |
| Tests | **Pytest** + **pytest-asyncio** + **Playwright** | Stack padrão Python/web |

**Posicionamento competitivo:**
- vs **LangSmith**: foco em event sourcing + replay determinístico (eles têm trace, não têm replay bit-a-bit).
- vs **Langfuse** (OSS): UI open-source mais completa, judge assíncrono, replay via Postgres nativamente.
- vs **Helicone**: temos tracing + replay, eles só proxy/cache.
- vs **Datadog APM**: cobertura semântica `genai.*` nativa, não adaptamos HTTP traces manualmente.

---

## 1. Problema

Agentes LLM em produção falham de formas que logs e APMs tradicionais não capturam:

| Pergunta | APM tradicional | LangSmith / Helicone | **Este produto** |
|---|---|---|---|
| Por que o agente falhou nesta run? | Traces genéricos | Trace visual | Atribuição causal por node |
| Qual tool custou mais? | Não sabe | Soma de tokens | Custo por tool × step × agente |
| Onde o handoff deu errado? | Não vê | Não modela | Grafo de handoff com success rate |
| Qual prompt regrediu a qualidade? | N/A | Diff manual | Comparação A/B automática |
| Reproduzir uma run de ontem? | Impossível | Re-executa (não-determinístico) | Replay **bit-a-bit** |

A maioria dos engenheiros sabe construir o agente. Quase nenhum sabe explicar por que ele degradou em produção 3 semanas depois.

## 2. Personas

**P1 — Engenheiro de agente (usuário diário).** Faz deploy de LangGraph na sexta. Segunda recebe tickets "o agente ficou lento". Precisa de: trace por run, custo por tool, diff de versão de prompt.

**P2 — Tech lead / manager (semanal).** Precisa responder: "está dentro do orçamento?" e "qual agente tem pior taxa de sucesso?". Quer: dashboard com SLOs, ranking de agentes, alertas.

**P3 — Engenheiro de plataforma (power user).** Integra a plataforma ao cluster LangGraph existente, query API, export para data warehouse.

## 3. Não-objetivos (v1)

- Não é eval framework (não substituirá Braintrust / LangSmith Evals).
- Não é prompt IDE (não substituirá LangSmith Playground).
- Não otimiza custo de LLM (só **mede**).
- Não tem UI de prompt engineering.
- Não suporta fine-tuning ou RLHF.

## 4. Casos de uso canônicos

### UC1 — Failure forensics
"Ontem às 14:32 um usuário reclamou que o agente entrou em loop." O engenheiro cola o `run_id` e vê: call 7 → tool `search` retornou erro → planner não replanejou → loop em `search → search → search`. Root cause em <2 min.

### UC2 — Cost attribution por tool
"O custo com LLM subiu 40% em 7 dias." Dashboard mostra: tool `browser_fetch` foi chamada 3x mais; chamada individual cresceu 2x em tokens (provavelmente schema prompt inchou). Evidência: diff de versão de prompt do executor.

### UC3 — Handoff diff
"No squad multiagente, security→perf caiu de 95% pra 60% de sucesso." Grafo de handoff destaca a aresta em vermelho. Click mostra: agente `perf` retornou JSON inválido 4x — bug introduzido no commit `abc123`.

### UC4 — Regression detection
"Troquei o prompt do planner de v3 pra v4. Ficou melhor?" Comparação automática: 200 runs sintéticas, mesmo input, judge LLM-as-judge, score v3=0.72, v4=0.81. Decisão: promover.

### UC5 — Replay determinístico
"Quero reproduzir exatamente a run `r_8f2a` para debugar." Replay consome checkpoints do `PostgresSaver` + mock determinístico do LLM + replay dos eventos de tool. Output idêntico a 100%.

## 5. Requisitos funcionais

### 5.1 Ingestão (must-have v1)
- **OTel-native:** SDK Python que cria spans compatíveis com OpenTelemetry semântico (`genai.*`).
- **Decorator wrapping:** `@observe(agent="planner")`, `@observe(tool="search")`, `@observe(llm="gpt-4o")`. Zero-touch em código existente.
- **LangGraph drop-in:** `GraphTracer` que escuta `PostgresSaver` checkpoints e captura state machine completo.
- **Multi-agent aware:** `handoff(from=A, to=B, payload=...)` captura grafo, não só lista.
- **Streaming:** ingest via OTLP gRPC, batch fallback HTTP.

### 5.2 Storage (must-have v1)
- **Events table** (Postgres, append-only): `run_id, parent_span_id, type, payload, ts`. Event sourcing puro.
- **Checkpoints table** (Postgres, FK `run_id`): snapshot do state LangGraph a cada step.
- **Metrics** (ClickHouse): colunar, agregações O(1) para cost/token/latency por dimensões.
- **Artifacts** (S3 / disk): raw LLM I/O, tool responses, embedding de inputs para similarity search.

### 5.3 Query API (must-have v1)
- `GET /runs?agent=X&status=failed&since=24h` → lista paginada.
- `GET /runs/{id}/trace` → árvore de spans estilo Jaeger.
- `GET /runs/{id}/replay` → URL para UI de replay.
- `POST /compare` → body com 2 `run_id`s, retorna diff semântico.
- `POST /score` → judge assíncrono com LLM-as-judge.

### 5.4 UI (must-have v1)
- **Trace view:** árvore expansível, payload de cada span, latência por nó.
- **Cost view:** waterfall por run, top tools por custo semanal, heatmap tool × versão de prompt.
- **Handoff view:** grafo direcionado, coloração por success rate, click na aresta abre runs.
- **Replay view:** stepper (prev/next) com state diff, mock toggle, replay button.
- **Diff view:** side-by-side 2 runs, judge scores, payloads anotados.

### 5.5 SLOs e alertas (nice-to-have v1, must-have v2)
- Definição: `success_rate{agent} > 0.9`, `p95_cost_per_run{agent} < $0.05`, `handoff_success{from=A,to=B} > 0.85`.
- Canal: webhook + Slack.

## 6. Requisitos não-funcionais

| Dimensão | Meta v1 |
|---|---|
| Ingestão overhead | <5% latência adicional no agente |
| Throughput | 1000 spans/s sustentado |
| Query `/trace` | p95 < 300ms para run com até 500 spans |
| Storage de 1 run (média) | <50 KB metadata + artifacts |
| Retention | 30 dias hot, 1 ano cold (S3) |
| Uptime SLO | 99.5% (consistente com deps OTel collector) |

## 7. Modelo de dados (núcleo)

```sql
-- Event sourcing: cada interação vira um evento
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    parent_span_id TEXT,
    type TEXT NOT NULL,        -- 'llm.call' | 'tool.invoke' | 'handoff' | 'checkpoint'
    agent TEXT,
    tool TEXT,
    payload JSONB NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    tokens_in INT,
    tokens_out INT,
    cost_usd NUMERIC(10,6),
    error TEXT
);

CREATE INDEX idx_events_run ON events(run_id, started_at);
CREATE INDEX idx_events_type_time ON events(type, started_at);

-- Checkpoint do state machine
CREATE TABLE checkpoints (
    run_id UUID NOT NULL,
    step INT NOT NULL,
    state JSONB NOT NULL,
    thread_id TEXT,
    saved_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, step)
);

-- Versão de artefatos (prompt, código)
CREATE TABLE artifacts (
    id BIGSERIAL PRIMARY KEY,
    type TEXT,         -- 'prompt' | 'agent_code'
    hash TEXT,
    version TEXT,
    content TEXT,
    created_at TIMESTAMPTZ
);
```

## 8. Arquitetura

```
┌────────────────┐
│ LangGraph /    │
│ Agentes users  │
└───────┬────────┘
        │ OpenTelemetry SDK
        ▼
┌────────────────┐     OTLP      ┌─────────────────┐
│ OTel Collector │──────────────▶│ Ingest API      │
│ (autoscaling)  │               │ FastAPI + Pydantic v2
└────────────────┘               └────────┬────────┘
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                   ┌─────────────┐ ┌─────────────┐ ┌──────────┐
                   │   Redpanda  │ │  Postgres   │ │  Redis   │
                   │  (buffer)   │ │ events+ckpt │ │ (cache)  │
                   └──────┬──────┘ │ +pgvector   │ └────┬─────┘
                          │        └──────┬──────┘      │
                          ▼               ▼             │
                   ┌─────────────┐ ┌─────────────┐       │
                   │ ClickHouse  │ │   Tempo     │       │
                   │   Cloud     │ │  (Grafana)  │       │
                   └──────┬──────┘ └──────┬──────┘       │
                          │               │             │
                          └───────┬───────┴─────────────┘
                                  ▼
                            ┌───────────────┐
                            │ Judge Worker  │
                            │ (Argo Workflows)│
                            └───────┬───────┘
                                    ▼
                       ┌────────────────────────┐
                       │ Query API (FastAPI)    │
                       │ + Sentry + Highlight   │
                       └────────────┬───────────┘
                                    ▼
                       ┌────────────────────────┐
                       │ Next.js + shadcn        │
                       │ + React Flow            │
                       │ (deploy: Vercel)        │
                       └────────────────────────┘

 Deploy backend: Fly.io · CI: GitHub Actions · Auth: Clerk
```

Componentes críticos:
- **`GraphTracer`** (lib Python + decorator): instrumenta LangGraph via callbacks de `PostgresSaver`. Stateless, idempotente. Distribuído via **PyPI**.
- **`ReplayEngine`**: recebe `run_id`, reconstrói state via checkpoints + cache Redis de artifacts, mock opcional de tool/LLM determinístico (seed fixo).
- **`JudgeService`**: worker **Argo Workflows** que roda LLM-as-judge em runs novas. Cache em Redis por `sha256(input, output)`. Reuso entre runs idênticos.
- **`IngestAPI`**: FastAPI async, validação Pydantic v2, OTLP receiver custom + REST fallback.
- **`TempoExporter`**: push para Grafana Tempo para visualização de trace estilo Jaeger sem custo por seat.

## 9. Métricas de sucesso do produto (não do agente)

- **Adoção:** número de `run_id`s ingeridos por dia. Meta v1: 100k/dia sustentável.
- **Latência de diagnóstico:** tempo entre "bug reportado" e "root cause identificado". Meta: <30 min para runs das últimas 24h.
- **Cobertura:** % de agentes da empresa instrumentados. Meta: >80% em 60 dias.
- **NPS interno** entre P1, P2, P3. Meta: >40.

## 10. Marcos (12 semanas)

| Semana | Entrega |
|---|---|
| 1–2 | Event model + ingest API + SDK `@observe` básico |
| 3–4 | Postgres schema + storage + query `/trace` |
| 5–6 | `GraphTracer` para LangGraph + replay engine |
| 7–8 | UI: trace view + replay view (Next.js) |
| 9–10 | Cost attribution + handoff graph + diff view |
| 11 | Judge service + LLM-as-judge assíncrono |
| 12 | Docs, demo dataset, post público |

## 11. Riscos

- **Custo de storage cresce exponencialmente com volume.** Mitigação: sampling adaptativo (100% de erros, 10% de sucessos).
- **Determinismo de replay é ilusório** se LLMs não forem mockáveis. Mitigação: replay só é "exato" no caminho de tools; juiz usa mesmo modelo + cache de judge por hash.
- **OpenTelemetry semântico para GenAI ainda está instável** (`genai.*` mudou entre versões). Mitigação: fixar versão semver, rastrear upstream.
- **Privacidade:** payloads podem conter PII do usuário. Mitigação: opt-in por redação no ingest, retention curta para payloads raw, hash-only para artefatos sensíveis.

## 12. Fora de escopo v1

- Auto-instrumentação para outros frameworks (CrewAI, AutoGen) — só LangGraph.
- Multi-tenant billing.
- Real-time alerting complexo.
- Integração com Datadog/New Relic (export OTLP genérico já cobre).

---

## 13. Por que este stack é "de portfólio"

Cada ferramenta escolhida tem nome no mercado. Em entrevista, o entrevistador reconhece:
- "Então você sabe que **Langfuse** já faz parte disso — o que você fez diferente?"
- "Já usou **Tempo** em produção? Onde?"
- "Por que **Argo** e não **Temporal**?"

Respostas concretas (não slogans):
- Langfuse não tem replay determinístico e usa Postgres só pra metadata.
- Tempo ganha de Jaeger em storage e de Datadog em custo.
- Argo é K8s-native; Temporal é state machine-as-code mas exige infra própria — escolhi Argo porque o judge é linear, não orquestração complexa.

**Demonstrações de mercado (links de referência):**
- OpenTelemetry GenAI SIG: https://opentelemetry.io/community/
- Langfuse: https://langfuse.com (referência arquitetural OSS)
- Helicone: https://helicone.ai (referência de proxy)
- LangGraph checkpointing docs: https://langchain-ai.github.io/langgraph/concepts/persistence/
- Grafana Tempo: https://grafana.com/oss/tempo/
- ClickHouse observability case studies: https://clickhouse.com/use-cases/observability

---

## Anexo A — Post público derivado

**Título:** *"Construí um Datadog para agentes de IA. Consigo reproduzir qualquer execução, medir custo por tool e encontrar regressões em minutos."*

**Tese:**
1. APM tradicional falha em agentes porque a unidade de trabalho não é o request — é o **step de raciocínio**.
2. Event sourcing + checkpoint storage habilita replay determinístico que nenhum concorrente entrega.
3. Custo e qualidade devem ser tratados como **first-class observability signals**, não como afterthoughts.
4. Diff de versões de prompt por A/B contínuo é o único caminho real para evitar regressões silenciosas.

**Estrutura:**
- Hook: "Seu agente vendeu R$0 em Black Friday porque entrou em loop. Logs não disseram por quê."
- Conceito: event sourcing + tracing semântico.
- Demo: 3 telas (trace, handoff graph, replay).
- Resultado: detectou regressão de prompt em 4 min (narrativa real ou sintética crível).
- CTA: github link + demo ao vivo.
