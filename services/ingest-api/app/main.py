from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .auth import TokenStore
from .errors import IngestError
from .health import (
    KafkaHealth, PostgresHealth, RedisHealth, run_checks,
)
from .observability import init_sentry
from .persistence.memory_bus import InMemoryBus
from .persistence.memory_store import InMemoryStore
from .pipeline import PipelineDeps
from .ratelimit import RateLimiter
from .receivers import rest as rest_receiver
from .tracing import init_metrics, init_tracing


logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    store: InMemoryStore
    bus: InMemoryBus
    token_store: TokenStore
    deps: PipelineDeps
    postgres_dsn: str | None = None
    kafka_brokers: str | None = None
    clickhouse_url: str | None = None


def create_app(
    store: InMemoryStore | None = None,
    bus: InMemoryBus | None = None,
    token_store: TokenStore | None = None,
    pii_mode: str = "redact",
    enable_sentry: bool = True,
    health_checks: list | None = None,
    postgres_dsn: str | None = None,
    kafka_brokers: str | None = None,
    clickhouse_url: str | None = None,
) -> FastAPI:
    if enable_sentry:
        init_sentry()

    postgres_dsn = postgres_dsn if postgres_dsn is not None else os.environ.get("POSTGRES_DSN")
    if postgres_dsn:
        from .persistence.postgres.store import PostgresStore
        store = PostgresStore(postgres_dsn)
    else:
        store = store or InMemoryStore()

    if kafka_brokers or os.environ.get("KAFKA_BROKERS"):
        from .persistence.kafka.bus import KafkaBus
        bus = KafkaBus(bootstrap_servers=kafka_brokers or os.environ["KAFKA_BROKERS"])
    else:
        bus = bus or InMemoryBus()

    ctx = AppContext(
        store=store,
        bus=bus,
        token_store=token_store or TokenStore(),
        deps=None,
        postgres_dsn=postgres_dsn,
        kafka_brokers=kafka_brokers,
        clickhouse_url=clickhouse_url,
    )
    ctx.deps = PipelineDeps(
        store=ctx.store,
        bus=ctx.bus,
        rate_limiter=RateLimiter(),
        pii_mode=pii_mode,
    )

    app = FastAPI(
        title="ingest-api",
        version=os.environ.get("SENTRY_RELEASE", "0.1.0"),
        docs_url="/docs" if os.environ.get("DOCS_ENABLED", "1") == "1" else None,
        redoc_url=None,
    )

    app.dependency_overrides[rest_receiver._get_ctx] = lambda: ctx
    app.dependency_overrides[rest_receiver._get_token_store] = lambda: ctx.token_store
    app.state.ctx = ctx

    app.include_router(rest_receiver.router)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(IngestError)
    async def ingest_error_handler(request: Request, exc: IngestError):
        rid = getattr(request.state, "request_id", "unknown")
        body = exc.to_dict(rid)
        if exc.status == 429 and "retry_after_s" in exc.details:
            return JSONResponse(
                body, status_code=exc.status, headers={"Retry-After": str(exc.details["retry_after_s"])}
            )
        return JSONResponse(body, status_code=exc.status)

    @app.get("/v1/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/v1/readyz")
    async def readyz():
        checks = health_checks or [
            PostgresHealth(None),
            RedisHealth(None),
            KafkaHealth(None),
        ]
        report = await run_checks(checks)
        status_code = 200 if report["status"] == "ok" else 503
        return JSONResponse(report, status_code=status_code)

    @app.on_event("startup")
    async def _connect_store():
        connect = getattr(ctx.store, "connect", None)
        if connect:
            await connect()

    @app.on_event("shutdown")
    async def _close_store():
        close = getattr(ctx.store, "close", None)
        if close:
            await close()

    init_tracing(app)
    init_metrics(app)

    return app


app = create_app()
