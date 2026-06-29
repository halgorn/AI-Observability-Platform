from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.health import KafkaHealth, PostgresHealth, RedisHealth, run_checks
from app.main import create_app
from app.persistence.memory_bus import InMemoryBus
from app.persistence.memory_store import InMemoryStore
from app.auth import TokenStore


def test_healthz_always_200():
    app = create_app(enable_sentry=False)
    c = TestClient(app)
    r = c.get("/v1/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_returns_degraded_when_dependencies_missing():
    app = create_app(enable_sentry=False, health_checks=[
        PostgresHealth("postgres://localhost:1/none"),
        RedisHealth("redis://localhost:1/0"),
    ])
    c = TestClient(app)
    r = c.get("/v1/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert "postgres" in body["checks"]
    assert "redis" in body["checks"]
    assert "latency_ms" in body["checks"]["postgres"]


def test_readyz_ok_when_no_dependencies_configured():
    app = create_app(enable_sentry=False, health_checks=[])
    c = TestClient(app)
    r = c.get("/v1/readyz")
    assert r.status_code == 200


def test_run_checks_runs_all_in_parallel():
    class FastCheck:
        name = "fast"
        async def check(self): return True, "ok"

    class SlowCheck:
        name = "slow"
        async def check(self):
            import asyncio
            await asyncio.sleep(0.5)
            return True, "ok"

    import time
    import asyncio
    async def run():
        start = time.perf_counter()
        report = await run_checks([FastCheck(), SlowCheck()])
        return report, time.perf_counter() - start

    report, elapsed = asyncio.run(run())
    assert elapsed < 0.6, f"checks should run in parallel, took {elapsed:.2f}s"
    assert report["status"] == "ok"


def test_observability_init_sentry_no_op_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    from app.observability import init_sentry
    init_sentry()
    from app.observability import _sentry_initialized
    assert _sentry_initialized is False


def test_observability_scrub_pii_strips_auth_header():
    from app.observability import _scrub_pii
    event = {
        "extra": {"api_key": "secret123"},
        "request": {"headers": {"authorization": "Bearer secret", "x-custom": "keep"}},
    }
    scrubbed = _scrub_pii(event, {})
    assert scrubbed["extra"]["api_key"] == "[REDACTED]"
    assert scrubbed["request"]["headers"]["authorization"] == "[REDACTED]"
    assert scrubbed["request"]["headers"]["x-custom"] == "keep"


def test_observability_capture_exception_no_sentry(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    from app.observability import init_sentry, capture_exception
    init_sentry()
    capture_exception(ValueError("test"))
