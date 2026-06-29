# 11 — Auth Domain

Clerk para UI, JWT verification no backend. Multi-tenant desde dia 1.

## Modelo

```
User (Clerk)
  └─ belongs to N Organizations
       └─ has Role: owner | admin | member | viewer
            └─ scoped to Org
```

## Roles

| Role | Pode | Não pode |
|---|---|---|
| `owner` | tudo + billing + delete org | — |
| `admin` | gerenciar membros, SLO, API keys | billing, delete org |
| `member` | ver runs, criar judge, replay, compare | gerenciar org |
| `viewer` | ver runs, dashboards | replay, judge, compare |

> Service tokens (SDK) **não** são user — vivem em `service_tokens` table com `org_id`, `scopes[]`, `expires_at`.

## JWT

- Issuer: `https://clerk.ai-obs.local`
- Algorithm: RS256
- Claims canônicos:
  - `sub` (user_id)
  - `org_id` (active org no momento)
  - `org_role`
  - `org_slug`
  - `iat`, `exp` (max 1h)
- Verificação no FastAPI via `clerk-backend-sdk` ou JWKS manual.

## Middleware FastAPI

```python
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/v1/healthz"):
        return await call_next(request)

    if request.url.path.startswith("/v1/traces") or \
       request.url.path.startswith("/v1/events"):
        token = await verify_service_token(request.headers["authorization"])
        request.state.org_id = token.org_id
        request.state.scopes = token.scopes
        return await call_next(request)

    claims = await verify_user_jwt(request.headers["authorization"])
    request.state.user_id = claims["sub"]
    request.state.org_id = claims["org_id"]
    request.state.role = claims["org_role"]
    return await call_next(request)
```

## Row-Level Security (Postgres)

```sql
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY runs_org_isolation ON runs
    USING (org_id = current_setting('app.org_id', true));
```

- Toda conexão ao Postgres seta `SET app.org_id = '...'`.
- Service tokens do mesmo org passam; cross-org = 0 rows.
- Admin/SQL raw bypassa com `SET app.bypass_rls = 'true'` (auditado).

## Scopes (service tokens)

| Scope | Permite |
|---|---|
| `ingest.write` | POST /v1/traces, POST /v1/events |
| `runs.read` | GET /v1/runs, /trace, /events |
| `runs.replay` | GET /v1/runs/{id}/replay |
| `judge.write` | POST /v1/runs/{id}/judge, /v1/score |
| `compare.read` | POST /v1/compare, GET /v1/compare |
| `admin.org` | GET/POST /v1/orgs/{id}/slo |

## API keys (service tokens)

```sql
CREATE TABLE service_tokens (
    id          UUID PRIMARY KEY,
    org_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    hash        TEXT NOT NULL,           -- sha256 do secret
    scopes      TEXT[] NOT NULL,
    last_used_at TIMESTAMPTZ,
    expires_at  TIMESTAMPTZ,
    created_by  TEXT NOT NULL,           -- user_id
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX idx_service_tokens_org ON service_tokens(org_id) WHERE revoked_at IS NULL;
```

- Secret mostrado **uma vez** no momento da criação.
- Storage = hash sha256 (token = 32 bytes random base64).
- Rotação recomendada a cada 90 dias (alerta no UI se > 180).

## UI — Clerk provider

```tsx
// app/layout.tsx
import { ClerkProvider } from '@clerk/nextjs';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en" className="dark">
        <body>{children}</body>
      </html>
    </ClerkProvider>
  );
}
```

- `<OrganizationSwitcher />` no header.
- `<UserButton />` no canto.
- Server components: `auth()` do `@clerk/nextjs/server` para claims.
- Client components: `useUser()`, `useOrganization()`.

## Proteção de rotas (middleware Next.js)

```ts
// middleware.ts
import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';

const isProtected = createRouteMatcher([
  '/runs(.*)',
  '/agents(.*)',
  '/tools(.*)',
  '/compare(.*)',
  '/settings(.*)',
]);

export default clerkMiddleware((auth, req) => {
  if (isProtected(req)) auth().protect();
});
```

## Audit log

```sql
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    org_id      TEXT NOT NULL,
    actor_id    TEXT NOT NULL,           -- user ou service_token
    actor_type  TEXT NOT NULL,           -- 'user' | 'service_token'
    action      TEXT NOT NULL,           -- 'run.replay', 'slo.update', etc.
    target      TEXT,                    -- 'run_xxx', 'slo_yyy'
    metadata    JSONB DEFAULT '{}'::jsonb,
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- Append-only.
- Retenção: 1 ano.
- Acessível só por `owner`/`admin`.

## Erros

| HTTP | code |
|---|---|
| 401 | `AUTH_MISSING` |
| 403 | `AUTH_FORBIDDEN` |
| 403 | `AUTH_ROLE_INSUFFICIENT` |
| 401 | `AUTH_TOKEN_EXPIRED` |
| 401 | `AUTH_TOKEN_INVALID` |

## O que este domínio **NÃO** decide

- Onde orgs são armazenados → Clerk (fonte externa) + `orgs` table (cache)
- Como API valida input → `09-api.md`
