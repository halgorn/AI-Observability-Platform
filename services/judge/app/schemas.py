"""Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Dimension = Literal["factuality", "relevance", "harmfulness", "coherence", "completeness"]


class JudgeRequest(BaseModel):
    run_id: str
    span_id: str | None = None
    dimensions: list[Dimension] = Field(default_factory=lambda: ["factuality"])
    n_judges: int = Field(default=3, ge=1, le=5)
    input: str | None = None
    output: str | None = None


class JobAccepted(BaseModel):
    job_id: str
    run_id: str
    dimensions: list[str]
    status: Literal["queued", "running", "done", "failed"] = "queued"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JudgeResultOut(BaseModel):
    model: str
    dimension: str
    score: float
    rationale: str
    cache_hit: bool
    prompt_version: str


class CompareRequest(BaseModel):
    run_a: dict
    run_b: dict
    dimension: Dimension = "factuality"
