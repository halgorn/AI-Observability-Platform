"""Judge service FastAPI app."""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .auth import ServiceToken, TokenError, TokenStore
from .cache import InMemoryCache
from .schemas import CompareRequest, JudgeRequest, JobAccepted
from .service import JudgeResult, JudgeService, StubJudgeClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = StubJudgeClient()
    cache = InMemoryCache()
    app.state.judge = JudgeService(client=client, cache=cache)
    yield


def _auth(request: Request, authorization: Optional[str]) -> str:
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


def create_app(*, token_store: TokenStore | None = None, judge: JudgeService | None = None) -> FastAPI:
    app = FastAPI(title="judge", version="0.1.0", lifespan=lifespan)
    app.state.token_store = token_store or TokenStore()
    if judge is not None:
        app.state.judge = judge
    app.state.jobs: dict[str, JobAccepted] = {}
    app.state.results: dict[str, list[JudgeResult]] = {}

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

    @app.post("/v1/score", response_model=JobAccepted)
    async def enqueue_score(body: JudgeRequest, request: Request, authorization: Optional[str] = Header(default=None)):
        _auth(request, authorization)
        if not body.input or not body.output:
            raise HTTPException(status_code=400, detail={"code": "SCHEMA_INVALID", "message": "input and output required"})
        job_id = str(uuid.uuid4())
        job = JobAccepted(job_id=job_id, run_id=body.run_id, dimensions=body.dimensions, status="queued")
        app.state.jobs[job_id] = job
        import asyncio
        asyncio.create_task(_run_job(app, job_id, body))
        return job

    @app.get("/v1/jobs/{job_id}")
    async def get_job(job_id: str, request: Request, authorization: Optional[str] = Header(default=None)):
        _auth(request, authorization)
        job = app.state.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"job {job_id}"})
        results = app.state.results.get(job_id, [])
        return {**job.model_dump(), "results": [r.to_dict() for r in results]}

    @app.get("/v1/runs/{run_id}/judge")
    async def list_results(run_id: str, request: Request, authorization: Optional[str] = Header(default=None)):
        _auth(request, authorization)
        results = [r for r in app.state.results.values() for r in r if getattr(r, "model", None)]
        out = [r.to_dict() for entries in app.state.results.values() for r in entries]
        return {"items": out, "count": len(out)}

    @app.post("/v1/compare")
    async def compare(body: CompareRequest, request: Request, authorization: Optional[str] = Header(default=None)):
        _auth(request, authorization)
        judge: JudgeService = request.app.state.judge
        result = await judge.compare_runs(
            run_a=body.run_a, run_b=body.run_b, dimension=body.dimension,
        )
        return result

    return app


async def _run_job(app, job_id: str, body: JudgeRequest) -> None:
    job = app.state.jobs[job_id]
    job.status = "running"
    judge: JudgeService = app.state.judge
    results: list[JudgeResult] = []
    for dim in body.dimensions:
        try:
            r = await judge.judge(input=body.input, output=body.output, dimension=dim)
            results.append(r)
        except Exception as e:
            logger.warning("judge %s failed: %s", dim, e)
    app.state.results[job_id] = results
    job.status = "done"


app = create_app()
