"""Analytics routes: cost, handoff, diff."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from ..analytics import build_handoff_graph, compute_cost_diff, parse_window, render_sql
from ..auth import TokenError, TokenStore
from .query import _auth

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/v1/agents/handoffs")
async def list_handoffs(
    request: Request,
    since: str = Query(default="7d", description="Window like '24h', '7d', '30d'"),
    agent: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
):
    token = _auth(request, authorization)
    store = request.app.state.store
    days = parse_window(since)
    events = await store.fetch_handoffs(org_id=token.org_id, days=days, agent=agent)
    return {"items": build_handoff_graph(events), "since": since, "count": len(events)}


@router.get("/v1/cost/by_agent")
async def cost_by_agent(
    request: Request,
    since: str = Query(default="7d"),
    authorization: Optional[str] = Header(default=None),
):
    token = _auth(request, authorization)
    days = parse_window(since)
    sql = render_sql("by_agent", days, token.org_id)
    rows = await request.app.state.store.query_raw(sql)
    return {"items": rows, "since": since}


@router.get("/v1/cost/by_tool")
async def cost_by_tool(
    request: Request,
    since: str = Query(default="7d"),
    authorization: Optional[str] = Header(default=None),
):
    token = _auth(request, authorization)
    days = parse_window(since)
    sql = render_sql("by_tool", days, token.org_id)
    rows = await request.app.state.store.query_raw(sql)
    return {"items": rows, "since": since}


@router.get("/v1/cost/by_prompt")
async def cost_by_prompt(
    request: Request,
    since: str = Query(default="7d"),
    authorization: Optional[str] = Header(default=None),
):
    token = _auth(request, authorization)
    days = parse_window(since)
    sql = render_sql("by_prompt", days, token.org_id)
    rows = await request.app.state.store.query_raw(sql)
    return {"items": rows, "since": since}


@router.get("/v1/cost/by_day")
async def cost_by_day(
    request: Request,
    since: str = Query(default="7d"),
    authorization: Optional[str] = Header(default=None),
):
    token = _auth(request, authorization)
    days = parse_window(since)
    sql = render_sql("by_day", days, token.org_id)
    rows = await request.app.state.store.query_raw(sql)
    return {"items": rows, "since": since}


def _parse_window_unused(s: str) -> int:
    return parse_window(s)
