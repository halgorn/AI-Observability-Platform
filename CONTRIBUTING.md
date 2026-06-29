# Contributing

Thanks for your interest in contributing. This project is spec-driven — every change must respect the contracts in [`specs/`](./specs).

## Quick links

- [PRD](./prd.md) — what we're building and why
- [Spec design system](./specs/README.md) — start here for the architecture
- [Conformance rules](./specs/domains/15-conformance.md) — what "done" means
- [Open issues](https://github.com/halgorn/AI-Observability-Platform/issues) — what needs help
- [Roadmap](#roadmap) — what's next

## First-time contributors

Look for issues labeled [`good first issue`](https://github.com/halgorn/AI-Observability-Platform/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22). Start with one of those to get familiar with the spec → code → test loop.

## Workflow

```
1. Pick or open an issue
2. Comment "I'll take this" (avoids duplicate work)
3. Branch: git checkout -b fix/short-name  (or feat/, spec/, docs/, test/)
4. Make the change
5. Run make spec-lint && make test-ingest
6. Open PR using .github/PULL_REQUEST_TEMPLATE.md
7. Wait for review from CODEOWNERS
8. Merge after approval
```

## Rules of the road

### Spec changes are first-class

If your PR changes anything under `specs/`, you must:

1. Update the schema version (`.v2`) if it's a breaking change.
2. Add or update an ADR in `specs/decisions/`.
3. Update `specs/00-glossary.md` if you added an error code.
4. Update fixtures in `specs/fixtures/` so contract tests pass.

The `spec-guard` CI workflow will check the basics, but the real check is human review by the relevant domain owner (see CODEOWNERS in `specs/domains/15-conformance.md`).

### Tests are not optional

- New service → pytest suite with ≥ 80% coverage.
- New event type → fixture in `specs/fixtures/<your-agent>/valid/` and a contract test.
- Bug fix → regression test that fails before your fix and passes after.

### Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(sdk): add @observe decorator for tool calls
fix(ingest): handle missing parent_span_id in OTLP conversion
spec(judge): add REPLAY_DIVERGED to ErrorCode enum
docs(readme): clarify PII mode values
test(replay): add divergence detection test
chore(ci): bump Python to 3.12 in workflow
```

## Local setup

```bash
git clone https://github.com/halgorn/AI-Observability-Platform
cd AI-Observability-Platform

# Spec linter (no install beyond jsonschema)
make spec-lint

# Ingest API
cd services/ingest-api
pip install -e ".[dev,observability]"
pytest tests/ --cov=app

# Run live
INGEST_API_SECRET=demo uvicorn app.main:app --port 8000
```

## Project structure

- `prd.md` — Product Requirements
- `specs/` — Design system (single source of truth, treated like code)
- `services/` — Production code, one folder per service
- `packages/` — Reusable libraries (SDK coming)
- `apps/` — User-facing applications (web coming)

Each service has its own `pyproject.toml` (or `package.json` for the web app) and is independently deployable.

## What we don't accept

- Changes that bypass the spec (e.g., a hardcoded event type not in the JSON Schema).
- New dependencies without justification in the PR description.
- Ad-hoc renaming of existing identifiers (breaks observability dashboards).
- Secrets, PII, or production credentials in commits.

## Questions?

Open an issue with the [`question`](https://github.com/halgorn/AI-Observability-Platform/issues/new?template=feature.md) label. We're friendly.
