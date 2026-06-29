"""Event type stubs (Pydantic) — used by SDK to validate locally before send."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "llm.call", "tool.invoke", "handoff", "checkpoint",
    "error", "judge.result", "run.start", "run.end",
    "step.start", "step.end", "artifact.link",
]


class Step(BaseModel):
    name: str
    agent: str


class LLMCall(BaseModel):
    model: str = Field(pattern=r"^[a-z0-9_-]+/[a-z0-9._:-]+$")
    tokens_in: int
    tokens_out: int
    cost_usd: float
    cache_hit: bool = False


class Handoff(BaseModel):
    from_agent: str = Field(alias="from")
    to_agent: str = Field(alias="to")
    reason: str
    payload: dict
