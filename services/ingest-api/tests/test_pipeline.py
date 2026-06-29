from __future__ import annotations

import pytest

from app.persistence.memory_bus import InMemoryBus
from app.persistence.memory_store import InMemoryStore
from app.pipeline import PipelineDeps, process_batch
from app.ratelimit import RateLimitConfig, RateLimiter
from . import make_event


@pytest.fixture
def deps():
    return PipelineDeps(
        store=InMemoryStore(),
        bus=InMemoryBus(),
        rate_limiter=RateLimiter(),
    )


def test_process_batch_accepts_valid(deps):
    events = [make_event(span_id=f"0aaa1bb0c0ffee0{i}") for i in range(3)]
    result = asyncio_run(process_batch(events, "org_1", deps))
    assert result.accepted == 3
    assert result.rejected == 0
    assert len(deps.store.all()) == 3
    assert len(deps.bus.by_topic("events.raw")) == 3


def test_process_batch_idempotent(deps):
    event = make_event()
    r1 = asyncio_run(process_batch([event], "org_1", deps))
    r2 = asyncio_run(process_batch([event], "org_1", deps))
    assert r1.accepted == 1
    assert r2.accepted == 0
    assert r2.rejected == 1
    assert len(deps.store.all()) == 1


def test_process_batch_dlq_on_invalid(deps):
    bad = {"run_id": "x", "span_id": "y", "type": "llm.call", "started_at": "2026-06-29T12:00:00Z", "payload": {}}
    result = asyncio_run(process_batch([bad], "org_1", deps))
    assert result.rejected == 1
    assert len(deps.bus.dlq) == 1


def test_process_batch_org_isolation_in_store(deps):
    e1 = make_event(span_id="0aaa1bb0c0ffeea1")
    e2 = make_event(span_id="0aaa1bb0c0ffeea2")
    asyncio_run(process_batch([e1], "org_A", deps))
    asyncio_run(process_batch([e2], "org_B", deps))
    assert all(ev.get("org_id") in ("org_A", "org_B") for ev in deps.store.all())


def test_rate_limit_blocks_when_exceeded():
    cfg = RateLimitConfig(requests_per_minute=60, burst=2)
    deps = PipelineDeps(
        store=InMemoryStore(),
        bus=InMemoryBus(),
        rate_limiter=RateLimiter(cfg),
    )
    e1 = make_event(span_id="0aaa1bb0c0ffeeb1")
    e2 = make_event(span_id="0aaa1bb0c0ffeeb2")
    e3 = make_event(span_id="0aaa1bb0c0ffeeb3")
    r1 = asyncio_run(process_batch([e1], "org_X", deps))
    r2 = asyncio_run(process_batch([e2], "org_X", deps))
    assert r1.accepted == 1
    assert r2.accepted == 1
    with pytest.raises(Exception, match="rate"):
        asyncio_run(process_batch([e3], "org_X", deps))


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
