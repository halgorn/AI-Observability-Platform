# 15 — Conformance

Como garantir que **código segue spec** e que **spec se mantém consistente** ao longo do tempo.

> Spec sem enforcement = documento de esperança. Esta spec é executada.

## 3 camadas de conformidade

```
┌─────────────────────────────────────────────┐
│ 1. Spec validation (CI)                     │
│    - JSON Schema lint                       │
│    - Cross-reference check                  │
│    - ADR/template lint                      │
├─────────────────────────────────────────────┤
│ 2. Contract tests (CI)                      │
│    - Producer/consumer schema match         │
│    - Property-based tests                   │
│    - Golden snapshots                       │
├─────────────────────────────────────────────┤
│ 3. Runtime conformance                      │
│    - Schema version header                  │
│    - Feature detection                      │
│    - Backward-compat probes                 │
└─────────────────────────────────────────────┘
```

## 1. Spec validation (CI)

### Tooling

- `ajv` (Node) + `jsonschema` (Python) para validar JSON Schemas
- `markdown-link-check` para wikilinks internos
- Custom linters em `specs/tools/`:
  - `validate_schemas.py` — todos os JSON Schemas parseiam
  - `check_refs.py` — refs internas existem
  - `check_enums.py` — glossary ↔ schema em sync
  - `check_agent_scopes.py` — agent cards → domains válidos

### Checks (rodar em todo PR)

```bash
# 1. JSON Schemas são válidos
python specs/tools/validate_schemas.py

# 2. Todos os paths referenciados em *.md existem
python specs/tools/check_refs.py

# 3. Enum em 00-glossary.md == enum em 02-event-schema.md
python specs/tools/check_enums.py

# 4. Agent cards referenciam apenas domínios que existem
python specs/tools/check_agent_scopes.py

# 5. ADR template está sendo seguido
python specs/tools/check_adrs.py
```

### Exemplo: `check_refs.py`

```python
import re, pathlib

ROOT = pathlib.Path("specs")
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
FILE_REF = re.compile(r"`([\w./-]+\.(?:md|json|yaml|py|ts))`")

def collect_refs(text):
    refs = set()
    refs.update(WIKILINK.findall(text))
    refs.update(FILE_REF.findall(text))
    return refs

def resolve(ref, current_file):
    if ref.endswith(".json") or ref.endswith(".md"):
        return (current_file.parent / ref).resolve()
    return None

# ... walk, check, exit(1) on broken refs
```

### Saída esperada

```
$ python specs/tools/check_refs.py
specs/agents/judge-agent.md:7 → domains/07-judge.md ✓
specs/agents/judge-agent.md:12 → specs/schemas/foo.json ✗ (not found)
FAIL: 1 broken reference
```

## 2. Contract tests

### Producer/consumer (Pact-style)

Cada agente tem **fixtures canônicas** em `specs/fixtures/<agent>/`:

```
specs/fixtures/ingest-agent/
├── valid/
│   ├── llm-call.json
│   ├── tool-invoke.json
│   ├── handoff.json
│   ├── error.json
│   └── run-end-failed.json
├── invalid/
│   ├── missing-required.json
│   ├── wrong-type.json
│   ├── extra-field.json
│   └── pii-in-strict.json
└── expected/
    ├── ingest-rejected.json
    └── dlq-message.json
```

### Property-based tests

- `hypothesis` (Python) para `Event` round-trip.
- `fast-check` (TS) para OpenAPI client.

```python
from hypothesis import given, strategies as st
from ai_obs.schemas import Event

@given(st.builds(Event))  # estratégia custom
def test_event_round_trip(event: Event):
    json = event.model_dump_json()
    event2 = Event.model_validate_json(json)
    assert event == event2
```

### Golden snapshots

- `tests/snapshots/` com output esperado de `to_dict()`, `to_otel()`, etc.
- Mudou snapshot = PR deve atualizar explicitamente (`--update-snapshots`).

### Onde rodam

```yaml
# .github/workflows/conformance.yml
on: [push, pull_request]
jobs:
  spec-validation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python specs/tools/validate_schemas.py
      - run: python specs/tools/check_refs.py
      - run: python specs/tools/check_enums.py
      - run: python specs/tools/check_agent_scopes.py

  contract-tests:
    runs-on: ubuntu-latest
    services:
      postgres: { ... }
      redis:    { ... }
    steps:
      - run: pytest specs/fixtures/ -v
      - run: pytest tests/contract/ -v
```

## 3. Runtime conformance

### Version negotiation

- Toda request ao API envia `X-Spec-Version: 1` (opcional, default = latest).
- Resposta inclui `X-Spec-Version: 1.0.0`.
- Server rejeita com `SPEC_VERSION_UNSUPPORTED` se major mismatch.

### Feature detection

- Client pode fazer `GET /v1/spec/manifest` para descobrir:
  - supported event types
  - supported dimensions
  - supported attributes
  - supported agent roles

```json
{
  "spec_version": "1.0.0",
  "event_types": ["llm.call", "tool.invoke", ...],
  "judge_dimensions": ["factuality", "relevance", ...],
  "agent_roles": ["planner", "executor", ...],
  "features": {
    "replay": true,
    "judge_cache": true,
    "pii_mode_strict": true,
    "data_residency": ["us-east-1", "eu-west-1", "sa-east-1"]
  }
}
```

### Backward compat probes

- Canary deploy envia evento `v0` e `v1` por 24h.
- Se erro de schema em `v0` > 0.1% → rollback.
- Se erro em `v1` > 0.01% → bloqueia promoção.

## Schema versioning

### Regras

| Mudança | Tipo | Versão |
|---|---|---|
| Adicionar campo opcional | compat | minor bump |
| Adicionar enum value | compat | minor bump |
| Adicionar endpoint | compat | minor bump |
| Remover campo | breaking | major bump + `/v2/` |
| Mudar tipo de campo | breaking | major bump + `/v2/` |
| Renomear campo | breaking | major bump + `/v2/` |
| Tighten validation (regex) | breaking | major bump |

### Coexistência

- `/v1/` e `/v2/` rodam simultaneamente por **6 meses** (configurável por endpoint).
- `/v1/` recebe apenas bugfixes, não features.
- Sunset comunicado em:
  - `X-Sunset-At` header (RFC 8594)
  - email para admins de org com > 0 reqs em `/v1/` na última semana

## Deprecation policy

| Coisa | Janela | Como anunciar |
|---|---|---|
| Endpoint | 6 meses | `Deprecation` + `Sunset` header |
| Header | 3 meses | `Deprecation` header |
| SDK method | 6 meses | `@deprecated` + warning em runtime |
| Event type | 12 meses (aceito, marcado) | `events.type` continua válido; UI mostra "legacy" |
| Judge dimension | 6 meses | cache invalidado, novos judge jobs não usam |
| Attribute key | 6 meses | `attributes.v1` continua aceitando |

## Conformance test matrix

| Spec | Cobertura |
|---|---|
| `event.v1.json` | 100% dos campos testados com valid + invalid |
| `event-types.v1.json` | 1 test por `type` |
| `attributes.v1.json` | regex + extension patterns |
| `judge-result.v1.json` | round-trip + boundary scores (0, 0.5, 1) |
| `span.v1.json` | OTLP example fixtures |
| `run.v1.json` | all `status` values |

## Métricas de conformidade

| Métrica | Target |
|---|---|
| Spec validation pass rate em main | 100% |
| Contract test pass rate em main | 100% |
| Spec drift (delta entre spec e código) | < 5% |
| `X-Spec-Version` mismatch em prod | < 0.1% |
| Sunset violations | 0 |

## CODEOWNERS (em `specs/.github/CODEOWNERS`)

```
# CODEOWNERS
/specs/domains/03-tracing.md         @team-tracing
/specs/domains/04-agent-orchestration.md @team-tracing
/specs/domains/05-replay.md          @team-replay
/specs/domains/06-cost.md            @team-cost
/specs/domains/07-judge.md           @team-judge
/specs/domains/08-storage.md         @team-platform
/specs/domains/09-api.md             @team-api
/specs/domains/10-ui.md              @team-ui
/specs/domains/11-auth.md            @team-platform
/specs/domains/12-infra.md           @team-platform
/specs/domains/13-sandbox.md         @team-platform
/specs/domains/14-data-governance.md @team-platform @legal
/specs/domains/15-conformance.md     @team-platform
/specs/schemas/                      @team-platform
/specs/00-glossary.md                @team-platform
/specs/01-naming-conventions.md      @team-platform
```

## O que este domínio **NÃO** decide

- O conteúdo da spec → outros domínios
- Quem aprova PRs → CODEOWNERS acima
- Onde CI roda → `12-infra.md`
