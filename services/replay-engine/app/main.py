"""Replay engine FastAPI app."""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .auth import TokenError, TokenStore
from .engine import ReplayEngine
from .schemas import MockToggleIn, ReplaySessionOut, ReplayStepOut
from .store.memory import InMemorySessionStore

logger = logging.getLogger(__name__)


def _auth(request: Request, authorization: str | None) -> str:
    ts: TokenStore = request.app.state.token_store
    if not authorization:
        raise HTTPException(status_code=401, detail={"code": "AUTH_MISSING", "message": "Authorization required"})
    try:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=403, detail={"code": "AUTH_FORBIDDEN", "message": "Bearer required"})
        t = ts.verify(token)
        return t.org_id
    except TokenError as e:
        raise HTTPException(status_code=403, detail={"code": "AUTH_FORBIDDEN", "message": str(e)})


def create_app(*, token_store: TokenStore | None = None) -> FastAPI:
    app = FastAPI(title="replay-engine", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        from fastapi.responses import JSONResponse
        origin = request.headers.get("origin")
        headers = {}
        if origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
            headers["Vary"] = "Origin"
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL", "message": str(exc)[:200]}},
            headers=headers,
        )

    app.state.token_store = token_store or TokenStore()
    app.state.session_store = InMemorySessionStore()
    app.state.engine = ReplayEngine(store=app.state.session_store)

    @app.middleware("http")
    async def rid_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        r = await call_next(request)
        r.headers["x-request-id"] = rid
        return r

    @app.get("/v1/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.post("/v1/runs/{run_id}/replay", response_model=ReplaySessionOut)
    async def start_replay(run_id: str, request: Request, authorization: str | None = Header(default=None)):
        org_id = _auth(request, authorization)
        events = []
        if hasattr(request.app.state, "query_client"):
            try:
                events = await request.app.state.query_client.fetch_run_events(run_id, org_id)
            except Exception as e:
                logger.warning("query fetch failed: %s", e)
        session = app.state.engine.load(run_id, events, [])
        session.steps[0].state["org_id"] = org_id
        app.state.session_store.save(session)
        return _to_out(session)

    @app.post("/v1/replay/{session_id}/step", response_model=ReplayStepOut)
    async def step_replay(session_id: str, request: Request, n: int = 1, authorization: str | None = Header(default=None)):
        _auth(request, authorization)
        try:
            step = await app.state.engine.step(session_id, n=n)
        except KeyError:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"session {session_id}"})
        return ReplayStepOut(
            step=step.step,
            state_hash=step.state_hash,
            diverged=step.diverged,
            divergence_detail=step.divergence_detail,
        )

    @app.post("/v1/replay/{session_id}/reset", response_model=ReplayStepOut)
    async def reset_replay(session_id: str, request: Request, to_step: int = 0, authorization: str | None = Header(default=None)):
        _auth(request, authorization)
        session = app.state.engine.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"session {session_id}"})
        session.current_step = max(0, min(to_step, session.total_steps))
        if session.steps:
            return ReplayStepOut(
                step=session.current_step,
                state_hash=session.steps[min(session.current_step, len(session.steps) - 1)].state_hash,
                diverged=False,
            )
        return ReplayStepOut(step=0, state_hash="sha256:" + "0" * 64, diverged=False)

    @app.post("/v1/replay/{session_id}/toggle", response_model=ReplaySessionOut)
    async def toggle_mock(session_id: str, body: MockToggleIn, request: Request, authorization: str | None = Header(default=None)):
        _auth(request, authorization)
        try:
            session = app.state.engine.toggle_mock(session_id, target=body.target, value=body.value)
        except KeyError:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"session {session_id}"})
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"code": "SCHEMA_INVALID", "message": str(e)})
        return _to_out(session)

    @app.post("/v1/replay/{session_id}/run", response_model=ReplaySessionOut)
    async def run_full(session_id: str, request: Request, authorization: str | None = Header(default=None)):
        _auth(request, authorization)
        try:
            session = await app.state.engine.replay_full(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"session {session_id}"})
        return _to_out(session)

    @app.get("/v1/replay/{session_id}/status", response_model=ReplaySessionOut)
    async def get_status(session_id: str, request: Request, authorization: str | None = Header(default=None)):
        _auth(request, authorization)
        session = app.state.engine.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"session {session_id}"})
        return _to_out(session)

    return app


def _to_out(session) -> ReplaySessionOut:
    return ReplaySessionOut(
        session_id=session.session_id,
        run_id=session.run_id,
        total_steps=session.total_steps,
        current_step=session.current_step,
        mock_llm=session.mock_llm,
        mock_tools=sorted(session.mock_tools),
        seed=session.seed,
        diverged_at=session.diverged_at,
        status=session.status,
    )


app = create_app()
