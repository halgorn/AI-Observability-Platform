"""Query API FastAPI app."""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .auth import TokenStore
from .db.store import QueryStore
from .routers import query as query_router

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
    app.state.token_store = token_store or TokenStore()
    if store is not None:
        app.state.store = store
    app.include_router(query_router.router)

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
