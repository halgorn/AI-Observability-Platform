"""Cost aggregation queries — mirrors specs/domains/06-cost.md §Storage.

Aggregations:
  cost_by_agent_day
  cost_by_tool
  cost_by_prompt_version
  top_tools
"""
from __future__ import annotations

from typing import Any, Optional


COST_QUERIES_SQL = {
    "by_agent": """
        SELECT agent, llm_model, prompt_version,
               sum(cost_usd) AS cost_usd_total,
               sum(tokens_in) AS tokens_in_total,
               sum(tokens_out) AS tokens_out_total,
               count(*) AS call_count
        FROM events_ch
        WHERE type = 'llm.call'
          AND started_at > now() - interval '$days days'
          AND org_id = $org_id
        GROUP BY agent, llm_model, prompt_version
        ORDER BY cost_usd_total DESC
    """,
    "by_tool": """
        SELECT tool, count(*) AS invocations,
               sum(CASE WHEN error_code IS NOT NULL THEN 1 ELSE 0 END) AS errors,
               sum(duration_ms) AS total_duration_ms
        FROM events_ch
        WHERE type = 'tool.invoke'
          AND started_at > now() - interval '$days days'
          AND org_id = $org_id
        GROUP BY tool
        ORDER BY invocations DESC
    """,
    "by_prompt": """
        SELECT prompt_version, count(DISTINCT run_id) AS runs,
               sum(cost_usd) AS cost_usd_total,
               avg(cost_usd) AS cost_usd_avg
        FROM events_ch
        WHERE type = 'llm.call'
          AND prompt_version IS NOT NULL
          AND started_at > now() - interval '$days days'
          AND org_id = $org_id
        GROUP BY prompt_version
        ORDER BY cost_usd_total DESC
    """,
    "by_day": """
        SELECT toDate(started_at) AS day,
               agent,
               sum(cost_usd) AS cost_usd_total,
               sum(tokens_in + tokens_out) AS tokens_total
        FROM events_ch
        WHERE type = 'llm.call'
          AND started_at > now() - interval '$days days'
          AND org_id = $org_id
        GROUP BY day, agent
        ORDER BY day DESC, cost_usd_total DESC
    """,
}


def render_sql(name: str, days: int, org_id: str) -> str:
    template = COST_QUERIES_SQL[name]
    return template.replace("$days", str(days)).replace("$org_id", org_id)


def build_handoff_graph(events: list[dict]) -> list[dict]:
    """Build a graph structure from handoff events.

    Returns list of edges: {from, to, success_count, total_count, success_rate}
    """
    edges: dict[tuple[str, str], dict] = {}
    for e in events:
        if e.get("type") != "handoff":
            continue
        p = e.get("payload", {})
        f, t = p.get("from"), p.get("to")
        if not f or not t:
            continue
        key = (f, t)
        if key not in edges:
            edges[key] = {"from": f, "to": t, "success_count": 0, "total_count": 0}
        edges[key]["total_count"] += 1
        if not e.get("error_code"):
            edges[key]["success_count"] += 1
    result = []
    for e in edges.values():
        total = e["total_count"]
        e["success_rate"] = e["success_count"] / total if total > 0 else 0.0
        result.append(e)
    return sorted(result, key=lambda x: -x["total_count"])


def compute_cost_diff(events_a: list[dict], events_b: list[dict]) -> dict:
    """Compare two runs' cost structure."""
    def totals(events):
        return {
            "cost_usd": sum((e.get("cost_usd") or 0) for e in events),
            "tokens_in": sum((e.get("tokens_in") or 0) for e in events),
            "tokens_out": sum((e.get("tokens_out") or 0) for e in events),
            "llm_calls": sum(1 for e in events if e.get("type") == "llm.call"),
            "tool_calls": sum(1 for e in events if e.get("type") == "tool.invoke"),
            "errors": sum(1 for e in events if e.get("error_code")),
        }
    a = totals(events_a)
    b = totals(events_b)
    return {
        "a": a,
        "b": b,
        "delta": {k: b[k] - a[k] for k in a},
        "ratio": {k: (b[k] / a[k] if a[k] else float("inf") if b[k] else 1.0) for k in a},
    }


def parse_window(s: str) -> int:
    s = s.strip().lower()
    try:
        if s.endswith("d"):
            return int(s[:-1])
        if s.endswith("h"):
            return max(1, int(s[:-1]) // 24)
        if s.endswith("m"):
            return max(1, int(s[:-1]) // (24 * 60))
        return int(s)
    except ValueError:
        return 7
