from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    requests_per_minute: int = 600
    burst: int = 100


class RateLimiter:
    """Per-org token bucket. In-memory; replace with Redis in prod (PRD §09-api)."""

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()
        self._buckets: dict[str, tuple[float, float]] = defaultdict(lambda: (self.config.burst, time.time()))

    def check(self, org_id: str) -> tuple[bool, int]:
        tokens, last = self._buckets[org_id]
        now = time.time()
        elapsed = now - last
        refill = (elapsed / 60.0) * self.config.requests_per_minute
        tokens = min(self.config.burst, tokens + refill)
        if tokens < 1:
            self._buckets[org_id] = (tokens, now)
            retry_after = max(1, int(60 / self.config.requests_per_minute))
            return False, retry_after
        self._buckets[org_id] = (tokens - 1, now)
        return True, 0
