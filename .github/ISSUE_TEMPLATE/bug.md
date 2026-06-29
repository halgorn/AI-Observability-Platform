---
name: Bug report
about: Something is broken
title: "[bug] "
labels: bug
assignees: ''
---

## What happened

<!-- A clear, concise description of the bug. -->

## Reproduction

```bash
# Minimal steps to reproduce
```

## Expected

<!-- What you expected to happen. -->

## Actual

<!-- What actually happened. Include error messages, stack traces, screenshots. -->

## Environment

- Service: [ingest-api / query-api / replay-engine / judge / web / sdk]
- Version / commit: <!-- e.g. v0.1.0 / abc1234 -->
- Python: <!-- e.g. 3.12.3 -->
- OS: <!-- e.g. Ubuntu 24.04 -->
- Deploy: <!-- e.g. Fly.io region iad -->

## Logs

```
<!-- Paste relevant logs. Sentry links are great. -->
```

## Checklist

- [ ] I searched existing issues and didn't find a duplicate
- [ ] I ran `make spec-lint` and `make test-ingest` and pasted results if relevant
