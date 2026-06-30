"""Query API FastAPI app."""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import TokenStore
from .db.store import QueryStore
from .routers import analytics as analytics_router
from .routers import query as query_router


CORS_ALLOW_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _cors_json(status: int, request: Request, body: dict) -> JSONResponse:
    origin = request.headers.get("origin")
    headers = {}
    if origin in CORS_ALLOW_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    return JSONResponse(status_code=status, content=body, headers=headers)

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    store: QueryStore
    token_store: TokenStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    dsn = os.environ.get("POSTGRES_DSN")
    if dsn:
        store = QueryStore(dsn)
        await store.connect()
        app.state.store = store
    yield
    if hasattr(app.state, "store"):
        await app.state.store.close()


def create_app(
    *,
    store: QueryStore | None = None,
    token_store: TokenStore | None = None,
    postgres_dsn: str | None = None,
) -> FastAPI:
    app = FastAPI(title="query-api", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return _cors_json(
            500,
            request,
            {"error": {"code": "INTERNAL", "message": str(exc)[:200]}},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return _cors_json(
            400,
            request,
            {"error": {"code": "BAD_REQUEST", "message": str(exc)[:200]}},
        )

    app.state.token_store = token_store or TokenStore()
    if store is not None:
        app.state.store = store
    app.include_router(query_router.router)
    app.include_router(analytics_router.router)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.get("/v1/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/v1/readyz")
    async def readyz():
        return {"status": "ok"}

    return app


app = create_app(postgres_dsn=os.environ.get("POSTGRES_DSN"))
