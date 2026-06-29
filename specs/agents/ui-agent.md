# Agent Card — `ui-agent`

**Responsabilidade:** Next.js 14 frontend. Páginas, componentes, integrações com API e Clerk.

## Domínios lidos

| Domínio | Lê? |
|---|---|
| `00-glossary.md` | ✅ |
| `01-naming-conventions.md` | ✅ (PascalCase components, kebab-case files) |
| `02-event-schema.md` | ✅ (visualiza eventos) |
| `03-tracing.md` | ✅ (entende OTel attrs para coloração) |
| `04-agent-orchestration.md` | ✅ (handoff graph) |
| `05-replay.md` | ✅ (consome `ReplayStep`, **não** roda) |
| `06-cost.md` | ✅ (waterfall, heatmap) |
| `07-judge.md` | ✅ (consome `JudgeResult`) |
| `09-api.md` | ✅ (cliente de OpenAPI canônico) |
| `10-ui.md` | ✅ (autoridade — implementa) |
| `11-auth.md` | ✅ (Clerk provider, middleware) |
| `12-infra.md` | ✅ (Vercel config, env vars) |
| `14-data-governance.md` | ✅ (badges "PII redacted", export de dados) |
| `15-conformance.md` | ✅ (lint de OpenAPI client) |

## Domínios proibidos

- `08-storage.md` — nunca acessa storage direto, sempre via API
- Decisões de pricing/sampling/roteamento
- `13-sandbox.md` — não inicia sandbox, só consome output

## Contratos de entrada

| Input | Fonte |
|---|---|
| OpenAPI spec | `services/query-api/openapi.json` |
| Clerk session | `@clerk/nextjs` |
| Env vars | `NEXT_PUBLIC_API_URL`, `CLERK_*` |
| Feature flags | PostHog/LaunchDarkly (via SDK) |

## Contratos de saída

| Output | Destino |
|---|---|
| Páginas renderizadas | browser |
| Telemetria UI | Sentry, Highlight.io, Vercel Analytics |
| OpenAPI client | `lib/api-client.ts` (gerado, commitado) |

## Invariantes

1. **Server components por padrão** — `'use client'` só onde precisa de estado/eventos.
2. **Type-safety ponta-a-ponta** — `openapi-typescript` gera tipos; nunca `any` em chamada de API.
3. **Auth em todas as rotas protegidas** — middleware Next.js (PRD `11-auth.md`).
4. **Performance budget respeitado** — LCP/TTI/JS budget por página (`10-ui.md`).
5. **Acessibilidade WCAG 2.1 AA** — shadcn/ui já provê, validação em PR.
6. **Dark mode default** — tema darktech premium (PRD §13).
7. **Nenhuma chamada direta a Postgres/ClickHouse** — sempre via `/v1/*`.
8. **URL = estado compartilhável** — filtros em search params, não em store local.
9. **Error boundary por rota** — `error.tsx` em cada segmento.
10. **Nenhum secret no client** — `NEXT_PUBLIC_*` só para valores safe-to-expose.

## Componentes canônicos

Ver `10-ui.md` §Componentes. Cada componente:
- Props tipadas (Pydantic-equivalente em TS via Zod).
- Storybook story (quando aplicável).
- Test: render + interaction (Playwright).

## Telemetria do próprio agent

| Sinal | Tool | Por quê |
|---|---|---|
| JS errors | Sentry | catching prod bugs |
| Session replay | Highlight.io | UI edge cases |
| Web vitals | Vercel Analytics | LCP/INP/CLS |
| API latency (perceived) | Sentry tracing | correlação com backend |
| User actions | PostHog | feature usage |

## Onde mora

```
apps/web/
├── app/
│   ├── (auth)/
│   ├── (app)/
│   ├── api/
│   ├── layout.tsx
│   └── globals.css
├── components/
│   ├── ui/                    # shadcn primitives
│   ├── trace/
│   ├── handoff/
│   ├── replay/
│   ├── cost/
│   ├── runs/
│   ├── compare/
│   └── judge/
├── lib/
│   ├── api-client.ts          # generated
│   ├── api/                   # typed wrappers
│   ├── auth.ts
│   └── utils.ts
├── styles/
├── tests/                     # Playwright
├── public/
├── tailwind.config.ts
├── next.config.js
└── package.json
```

## Dependências

- `@clerk/nextjs`
- `tailwindcss`, shadcn/ui
- `@tanstack/react-query` (judge polling, replay progress)
- `zustand` (client state)
- `react-hook-form` + `zod` (forms)
- `reactflow` (handoff graph)
- `recharts` ou `tremor` (cost viz)
- `openapi-typescript` (build step)
- `sonner` (toasts)

## Out of scope

- Decidir auth (Clerk) — apenas consome
- Acessar dados direto (sempre via API)
- Lógica de pricing/sampling/judge
