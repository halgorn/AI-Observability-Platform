"""Pydantic schemas for Query API responses."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


RunStatus = Literal["running", "succeeded", "failed", "timeout", "cancelled", "replaying"]


class RunSummary(BaseModel):
    run_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    thread_id: Optional[str] = None
    agent: str
    status: RunStatus
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    total_steps: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost_usd: Optional[float] = None
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    prompt_version: Optional[str] = None
    parent_run_id: Optional[str] = None
    tags: dict[str, str] = Field(default_factory=dict)


class RunEvent(BaseModel):
    run_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    type: str
    agent: Optional[str] = None
    tool: Optional[str] = None
    llm_model: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    error_code: Optional[str] = None
    payload: dict[str, Any]
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceNode(BaseModel):
    span_id: str
    parent_span_id: Optional[str] = None
    name: str
    kind: Literal["agent", "tool", "llm", "handoff", "checkpoint", "error"]
    duration_ms: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: Literal["ok", "error", "warning"]
    children: list["TraceNode"] = Field(default_factory=list)


class Trace(BaseModel):
    run_id: str
    agent: str
    status: RunStatus
    started_at: datetime
    duration_ms: int
    total_cost_usd: float
    root: TraceNode


class Checkpoint(BaseModel):
    step: int
    state_hash: str
    thread_id: Optional[str] = None
    saved_at: datetime


class RunsPage(BaseModel):
    items: list[RunSummary]
    next_cursor: Optional[str] = None
    total: Optional[int] = None


class SimilarRun(BaseModel):
    run_id: str
    agent: str
    similarity: float
    started_at: datetime


class ComparisonResult(BaseModel):
    run_a: str
    run_b: str
    dimension: Optional[str] = None
    diff: dict[str, Any]
