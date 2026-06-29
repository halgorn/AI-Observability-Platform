"""In-memory session store (Redis in prod — specs/domains/05-replay.md)."""
from __future__ import annotations

import json
import time
from typing import Optional

from ..session import ReplaySession


class InMemorySessionStore:
    def __init__(self) -> None:
        self._store: dict[str, ReplaySession] = {}
        self._by_run: dict[str, str] = {}

    def save(self, session: ReplaySession) -> None:
        self._store[session.session_id] = session
        self._by_run[session.run_id] = session.session_id

    def get(self, session_id: str) -> Optional[ReplaySession]:
        return self._store.get(session_id)

    def get_by_run(self, run_id: str) -> Optional[ReplaySession]:
        sid = self._by_run.get(run_id)
        return self._store.get(sid) if sid else None

    def lock_run(self, run_id: str, *, ttl_s: int = 3600) -> bool:
        if run_id in self._by_run:
            session = self._store.get(self._by_run[run_id])
            if session and (time.time() - session.started_at) < ttl_s:
                return False
        return True

    def count(self) -> int:
        return len(self._store)
