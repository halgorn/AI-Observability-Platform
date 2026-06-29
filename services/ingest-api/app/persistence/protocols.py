from __future__ import annotations

from typing import Protocol


class EventStore(Protocol):
    async def insert(self, event: dict) -> bool:
        """Insert event. Returns True if inserted, False if duplicate (idempotent)."""
        ...

    async def fetch_one(self, run_id: str, span_id: str) -> dict | None:
        ...


class EventBus(Protocol):
    async def publish(self, topic: str, event: dict) -> None: ...
    async def publish_dlq(self, event: dict, error: dict) -> None: ...
