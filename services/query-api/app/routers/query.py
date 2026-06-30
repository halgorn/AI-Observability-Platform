"""Routers: runs, trace, events, checkpoints, similar, compare."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request

from ..auth import ServiceToken, TokenError, TokenStore
from ..trace_builder import build_trace

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_id(run_id: str = Path(...)) -> str:
    try:
        return str(uuid.UUID(run_id))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_RUN_ID", "message": f"'{run_id}' is not a valid UUID"},
        )


def _auth(request: Request, authorization: Optional[str] = Header(default=None)) -> ServiceToken:
    ts: TokenStore = request.app.state.token_store
    if not authorization:
        raise HTTPException(status_code=401, detail={"code": "AUTH_MISSING", "message": "Authorization required"})
    try:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=403, detail={"code": "AUTH_FORBIDDEN", "message": "Bearer required"})
        return ts.verify(token)
    except TokenError as e:
        raise HTTPException(status_code=403, detail={"code": "AUTH_FORBIDDEN", "message": str(e)})


@router.get("/v1/runs")
async def list_runs(
    request: Request,
    agent: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200, ge=1),
    cursor: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
):
    token = _auth(request, authorization)
    store = request.app.state.store
    items, next_cursor = await store.list_runs(
        token.org_id, agent=agent, status=status, since=since, limit=limit, cursor=cursor,
    )
    return {"items": items, "next_cursor": next_cursor, "count": len(items)}


@router.get("/v1/runs/{run_id}")
async def get_run(
    request: Request,
    run_id: str = Path(...),
    authorization: Optional[str] = Header(default=None),
):
    run_id = _run_id(run_id)
    token = _auth(request, authorization)
    store = request.app.state.store
    summary = await store.fetch_run_summary(run_id, token.org_id)
    if not summary:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"run {run_id} not found"})
    return summary


@router.get("/v1/runs/{run_id}/trace")
async def get_trace(
    request: Request,
    run_id: str = Path(...),
    authorization: Optional[str] = Header(default=None),
):
    run_id = _run_id(run_id)
    token = _auth(request, authorization)
    store = request.app.state.store
    events = await store.fetch_run_events(run_id, token.org_id)
    if not events:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"run {run_id} not found"})
    return build_trace(events)


@router.get("/v1/runs/{run_id}/events")
async def get_events(
    request: Request,
    run_id: str = Path(...),
    authorization: Optional[str] = Header(default=None),
):
    run_id = _run_id(run_id)
    token = _auth(request, authorization)
    store = request.app.state.store
    events = await store.fetch_run_events(run_id, token.org_id)
    return {"items": events, "count": len(events)}


@router.get("/v1/runs/{run_id}/checkpoints")
async def get_checkpoints(
    request: Request,
    run_id: str = Path(...),
    authorization: Optional[str] = Header(default=None),
):
    run_id = _run_id(run_id)
    token = _auth(request, authorization)
    store = request.app.state.store
    cps = await store.fetch_checkpoints(run_id, token.org_id)
    return {"items": cps, "count": len(cps)}


@router.get("/v1/runs/{run_id}/similar")
async def get_similar_runs(
    request: Request,
    run_id: str = Path(...),
    limit: int = Query(default=10, le=50),
    authorization: Optional[str] = Header(default=None),
):
    run_id = _run_id(run_id)
    token = _auth(request, authorization)
    store = request.app.state.store
    similar = await store.similar_runs(run_id, token.org_id, limit=limit)
    return {"items": similar, "count": len(similar)}


@router.post("/v1/compare")
async def compare_runs(
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    token = _auth(request, authorization)
    body = await request.json()
    run_a = body.get("run_a")
    run_b = body.get("run_b")
    dimension = body.get("dimension")
    if not run_a or not run_b:
        raise HTTPException(status_code=400, detail={"code": "SCHEMA_INVALID", "message": "run_a and run_b required"})
    store = request.app.state.store
    events_a = await store.fetch_run_events(run_a, token.org_id)
    events_b = await store.fetch_run_events(run_b, token.org_id)
    diff = _diff_runs(events_a, events_b, dimension=dimension)
    return {
        "run_a": run_a,
        "run_b": run_b,
        "dimension": dimension,
        "diff": diff,
    }


def _diff_runs(events_a: list[dict], events_b: list[dict], *, dimension: Optional[str]) -> dict:
    cost_a = sum((e.get("cost_usd") or 0) for e in events_a)
    cost_b = sum((e.get("cost_usd") or 0) for e in events_b)
    tokens_a_in = sum((e.get("tokens_in") or 0) for e in events_a)
    tokens_b_in = sum((e.get("tokens_in") or 0) for e in events_b)
    duration_a = sum((e.get("duration_ms") or 0) for e in events_a)
    duration_b = sum((e.get("duration_ms") or 0) for e in events_b)
    errors_a = [e for e in events_a if e.get("error_code")]
    errors_b = [e for e in events_b if e.get("error_code")]
    return {
        "cost_usd": {"a": cost_a, "b": cost_b, "delta": cost_b - cost_a},
        "tokens_in": {"a": tokens_a_in, "b": tokens_b_in, "delta": tokens_b_in - tokens_a_in},
        "duration_ms": {"a": duration_a, "b": duration_b, "delta": duration_b - duration_a},
        "error_count": {"a": len(errors_a), "b": len(errors_b)},
        "events_count": {"a": len(events_a), "b": len(events_b)},
        "dimension": dimension,
    }
