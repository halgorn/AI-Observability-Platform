"""Pydantic schemas."""
from __future__ import annotations

from pydantic import BaseModel


class ReplaySessionOut(BaseModel):
    session_id: str
    run_id: str
    total_steps: int
    current_step: int
    mock_llm: bool
    mock_tools: list[str]
    seed: int
    diverged_at: int | None
    status: str


class ReplayStepOut(BaseModel):
    step: int
    state_hash: str
    diverged: bool
    divergence_detail: str | None = None


class MockToggleIn(BaseModel):
    target: str
    value: bool | str
