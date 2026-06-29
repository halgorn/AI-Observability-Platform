"""Custom Prometheus metrics for AI observability events."""
from __future__ import annotations

from typing import Any

try:
    from prometheus_client import Counter, Histogram

    _events_total = Counter(
        "ai_obs_events_total",
        "Total events processed",
        ["event_type", "agent", "model", "status"],
    )
    _cost_usd_total = Counter(
        "ai_obs_cost_usd_total",
        "Cumulative LLM cost in USD",
        ["event_type", "agent", "model"],
    )
    _tokens_total = Counter(
        "ai_obs_tokens_total",
        "Cumulative token count",
        ["agent", "model", "direction"],
    )
    _duration_ms = Histogram(
        "ai_obs_duration_ms",
        "Event processing duration in ms",
        ["event_type", "agent", "model"],
        buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000],
    )
    _ENABLED = True
except ImportError:
    _ENABLED = False


def record_event(event: dict[str, Any], *, status: str = "accepted") -> None:
    if not _ENABLED:
        return
    etype = event.get("type") or "unknown"
    agent = event.get("agent") or "unknown"
    model = (event.get("llm_model") or event.get("payload", {}).get("model") or "unknown")

    _events_total.labels(event_type=etype, agent=agent, model=model, status=status).inc()

    cost = event.get("cost_usd")
    if cost:
        _cost_usd_total.labels(event_type=etype, agent=agent, model=model).inc(float(cost))

    tokens_in = event.get("tokens_in")
    tokens_out = event.get("tokens_out")
    if tokens_in:
        _tokens_total.labels(agent=agent, model=model, direction="in").inc(int(tokens_in))
    if tokens_out:
        _tokens_total.labels(agent=agent, model=model, direction="out").inc(int(tokens_out))

    duration = event.get("duration_ms")
    if duration is not None:
        _duration_ms.labels(event_type=etype, agent=agent, model=model).observe(float(duration))
