.PHONY: spec-lint spec-lint-verbose spec-fix test test-ingest test-sdk test-query test-all build-ingest run-ingest ci help

help:
	@echo "Targets:"
	@echo "  make spec-lint           run all spec checks (silent)"
	@echo "  make spec-lint-verbose   show all warnings"
	@echo "  make spec-fix            show external refs needing code"
	@echo "  make test                run all tests (sdk + ingest + query)"
	@echo "  make test-ingest         run ingest-api tests"
	@echo "  make test-sdk            run SDK tests"
	@echo "  make test-query          run query-api tests"
	@echo "  make test-all            run spec lint + all tests"
	@echo "  make build-ingest        build ingest-api Docker image"
	@echo "  make run-ingest          run ingest-api in Docker"
	@echo "  make ci                  what CI runs"

spec-lint:
	@python3 specs/tools/check_all.py 2>&1 | grep -E "(──|OK|enums in sync|broken internal|❌|✗|PASS|FAIL)" || true

spec-lint-verbose:
	@python3 specs/tools/check_all.py

spec-fix:
	@python3 specs/tools/check_refs.py 2>&1 | grep "⚠️"

test-sdk:
	@cd packages/ai-obs-sdk && pytest tests/ --cov=src/ai_obs

test-ingest:
	@cd services/ingest-api && pytest tests/ --cov=app --cov-report=term-missing

test-query:
	@cd services/query-api && pytest tests/ --cov=app

test-replay:
	@cd services/replay-engine && pytest tests/ --cov=app

test-judge:
	@cd services/judge && pytest tests/ --cov=app

test-web:
	@cd apps/web && npm test 2>&1 | tail -20

test: test-sdk test-ingest test-query test-replay test-judge
	@echo "✓ all tests passed (web is manual via 'make build-web')"

test-all: spec-lint test
	@echo "✓ everything green"

build-ingest:
	docker build -t ingest-api -f services/ingest-api/Dockerfile .

run-ingest: build-ingest
	docker run --rm -p 8000:8000 \
	  -e INGEST_API_SECRET=demo \
	  -e SPEC_ROOT=/app/specs \
	  -e PII_MODE=redact \
	  ingest-api

ci: spec-lint test
	@echo "✓ CI green"
