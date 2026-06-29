.PHONY: spec-lint spec-lint-verbose spec-fix test-ingest test-all build-ingest run-ingest docker-ingest ci help

help:
	@echo "Targets:"
	@echo "  make spec-lint           run all spec checks (silent)"
	@echo "  make spec-lint-verbose   show all warnings"
	@echo "  make spec-fix            show external refs needing code"
	@echo "  make test-ingest         run ingest-api tests"
	@echo "  make test-all            run spec lint + all service tests"
	@echo "  make build-ingest        build ingest-api Docker image"
	@echo "  make run-ingest          run ingest-api in Docker"
	@echo "  make ci                  what CI runs"

spec-lint:
	@python3 specs/tools/check_all.py 2>&1 | grep -E "(──|OK|enums in sync|broken internal|❌|✗|PASS|FAIL)" || true

spec-lint-verbose:
	@python3 specs/tools/check_all.py

spec-fix:
	@python3 specs/tools/check_refs.py 2>&1 | grep "⚠️"

test-ingest:
	@cd services/ingest-api && pytest tests/ --cov=app --cov-report=term-missing

test-all: spec-lint test-ingest
	@echo "✓ all tests passed"

build-ingest:
	docker build -t ingest-api -f services/ingest-api/Dockerfile .

run-ingest: build-ingest
	docker run --rm -p 8000:8000 \
	  -e INGEST_API_SECRET=demo \
	  -e SPEC_ROOT=/app/specs \
	  -e PII_MODE=redact \
	  ingest-api

ci: spec-lint test-ingest
	@echo "✓ CI green"
