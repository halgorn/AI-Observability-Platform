"""ReplaySession — deterministic replay of a run via checkpoints."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReplayStep:
    step: int
    state: dict
    state_hash: str
    events: list[dict] = field(default_factory=list)
    diverged: bool = False
    divergence_detail: Optional[str] = None


@dataclass
class ReplaySession:
    session_id: str
    run_id: str
    total_steps: int
    current_step: int = 0
    mock_llm: bool = True
    mock_tools: set[str] = field(default_factory=set)
    seed: int = 0
    diverged_at: Optional[int] = None
    status: str = "ready"  # ready | replaying | done | diverged
    started_at: float = field(default_factory=time.time)
    steps: list[ReplayStep] = field(default_factory=list)

    @staticmethod
    def create(*, run_id: str, total_steps: int, seed: int | None = None) -> "ReplaySession":
        sid = str(uuid.uuid4())
        if seed is None:
            seed = int(hashlib.sha256(run_id.encode()).hexdigest()[:8], 16) % (2**31)
        return ReplaySession(session_id=sid, run_id=run_id, total_steps=total_steps, seed=seed)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "total_steps": self.total_steps,
            "current_step": self.current_step,
            "mock_llm": self.mock_llm,
            "mock_tools": sorted(self.mock_tools),
            "seed": self.seed,
            "diverged_at": self.diverged_at,
            "status": self.status,
            "started_at": self.started_at,
        }


def canonical_hash(obj: Any) -> str:
    """sha256 of canonical JSON serialization, ignoring None values."""
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items() if v is not None}
        if isinstance(o, list):
            return [_clean(x) for x in o]
        return o
    blob = json.dumps(_clean(obj), sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()
