---
name: Spec change
about: Change to specs/ — JSON Schemas, domains, or agents
title: "[spec] "
labels: spec
assignees: ''
---

## Type of change

- [ ] New event type (breaking — new `.v2` schema)
- [ ] New error code (non-breaking if appended)
- [ ] New domain spec
- [ ] New agent card
- [ ] ADR (Architecture Decision Record)
- [ ] Bug fix to existing spec
- [ ] Typo / formatting

## Files changed

<!-- List every file under specs/ that you touched. -->

## Backward compatibility

- [ ] Backward compatible (additive)
- [ ] Breaking — bumping version from X to Y
- [ ] Deprecation only — old path still works, marked for sunset

## Conformance

- [ ] `make spec-lint` passes
- [ ] `make test-ingest` passes
- [ ] If new schema: fixtures added under `specs/fixtures/`
- [ ] If new error code: `specs/00-glossary.md` and `specs/schemas/event.v1.json` updated together

## References

<!-- Link ADRs, prior discussion, related PRs. -->
