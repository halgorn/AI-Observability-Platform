"""ReplayEngine — orchestrates a replay session."""
from __future__ import annotations

import logging
from typing import Any, Optional

from .divergence import check_divergence
from .mock import MockLayer
from .session import ReplaySession, ReplayStep, canonical_hash

logger = logging.getLogger(__name__)


class ReplayEngine:
    def __init__(self, *, store: Any = None) -> None:
        self.store = store
        self._sessions: dict[str, ReplaySession] = {}

    def load(self, run_id: str, original_events: list[dict], original_checkpoints: list[dict]) -> ReplaySession:
        if not original_events and not original_checkpoints:
            raise ValueError(f"run {run_id} has no events or checkpoints")
        total = max(len(original_events), len(original_checkpoints))
        session = ReplaySession.create(run_id=run_id, total_steps=total)
        for cp in original_checkpoints:
            session.steps.append(ReplayStep(
                step=cp["step"],
                state={"thread_id": cp.get("thread_id")},
                state_hash=cp["state_hash"],
            ))
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[ReplaySession]:
        return self._sessions.get(session_id)

    def toggle_mock(self, session_id: str, *, target: str, value: bool | str) -> ReplaySession:
        session = self._require(session_id)
        if target == "llm":
            session.mock_llm = bool(value)
        elif target == "tool":
            if isinstance(value, str):
                if value == "":
                    session.mock_tools.clear()
                else:
                    session.mock_tools.add(value)
            else:
                session.mock_tools.add(target)
        else:
            raise ValueError(f"unknown mock target: {target}")
        return session

    async def step(self, session_id: str, n: int = 1) -> ReplayStep:
        session = self._require(session_id)
        session.status = "replaying"
        for _ in range(n):
            if session.current_step >= session.total_steps:
                session.status = "done"
                break
            replay_step = await self._execute_step(session, session.current_step)
            session.current_step += 1
        return session.steps[-1] if session.steps else ReplayStep(
            step=0, state={}, state_hash="sha256:0" * 64,
        )

    async def replay_full(self, session_id: str) -> ReplaySession:
        session = self._require(session_id)
        session.status = "replaying"
        while session.current_step < session.total_steps:
            await self._execute_step(session, session.current_step)
            session.current_step += 1
        session.status = "done" if session.diverged_at is None else "diverged"
        return session

    async def _execute_step(self, session: ReplaySession, step_idx: int) -> ReplayStep:
        if step_idx >= len(session.steps):
            step = ReplayStep(step=step_idx, state={}, state_hash=canonical_hash({}))
            session.steps.append(step)
        else:
            step = session.steps[step_idx]
        return step

    def _require(self, session_id: str) -> ReplaySession:
        s = self._sessions.get(session_id)
        if s is None:
            raise KeyError(f"session {session_id} not found")
        return s
