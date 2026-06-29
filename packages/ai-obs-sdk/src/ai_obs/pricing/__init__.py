"""Model pricing — mirror of specs/domains/06-cost.md §Pricing table."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

PRICING: dict[str, dict[str, Any]] = {
    "openai/gpt-4o-mini":      {"in": 0.000150, "out": 0.000600, "cache_in": 0.000075, "since": "2025-01-01"},
    "openai/gpt-4o":           {"in": 0.002500, "out": 0.010000, "cache_in": 0.001250, "since": "2025-01-01"},
    "openai/gpt-4-turbo":      {"in": 0.010000, "out": 0.030000, "cache_in": 0.005000, "since": "2025-01-01"},
    "anthropic/claude-3-5-sonnet":  {"in": 0.003000, "out": 0.015000, "cache_in": 0.000300, "since": "2025-01-01"},
    "anthropic/claude-3-5-haiku":   {"in": 0.000800, "out": 0.004000, "cache_in": 0.000080, "since": "2025-01-01"},
    "anthropic/claude-3-opus":      {"in": 0.015000, "out": 0.075000, "cache_in": 0.001500, "since": "2025-01-01"},
    "google/gemini-1.5-pro":   {"in": 0.001250, "out": 0.005000, "cache_in": 0.000313, "since": "2025-01-01"},
    "google/gemini-1.5-flash": {"in": 0.000075, "out": 0.000300, "cache_in": 0.000019, "since": "2025-01-01"},
}


def cost_of_call(*, model: str, tokens_in: int, tokens_out: int, at: datetime | None = None, cached: bool = False) -> float | None:
    p = PRICING.get(model)
    if p is None:
        return None
    in_rate = p["cache_in"] if cached else p["in"]
    cost = (Decimal(tokens_in) / 1000 * Decimal(str(in_rate))) + (Decimal(tokens_out) / 1000 * Decimal(str(p["out"])))
    return float(cost.quantize(Decimal("0.00000001")))
