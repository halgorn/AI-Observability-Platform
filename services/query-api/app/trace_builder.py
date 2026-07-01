"""Build a trace tree from flat event list."""
from __future__ import annotations

from typing import Any


def build_trace(events: list[dict]) -> dict:
    """Convert flat event list into a hierarchical tree.

    Roots are events with no parent_span_id. Children matched by parent_span_id.
    """
    by_id: dict[str, dict] = {}
    for ev in events:
        sid = ev.get("span_id")
        if not sid:
            continue
        by_id[sid] = {
            "span_id": sid,
            "parent_span_id": ev.get("parent_span_id"),
            "name": _span_name(ev),
            "kind": _kind(ev),
            "duration_ms": ev.get("duration_ms") or 0,
            "started_at": ev.get("started_at"),
            "ended_at": ev.get("ended_at"),
            "status": _status(ev),
            "children": [],
            "event": ev,
        }
    roots: list[dict] = []
    for node in by_id.values():
        parent_id = node["parent_span_id"]
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(node)
        else:
            roots.append(node)
    if not roots and by_id:
        roots = list(by_id.values())[:1]
    total_cost = sum((e.get("cost_usd") or 0) for e in events)
    total_duration = max((e.get("duration_ms") or 0) for e in events) if events else 0

    error_message: str | None = None
    error_type: str | None = None
    for e in events:
        if e.get("error_code") or e.get("type") == "error":
            attrs = e.get("attributes") or {}
            payload = e.get("payload") or {}
            error_message = attrs.get("error.message") or payload.get("message") or e.get("error_code")
            error_type = attrs.get("error.type") or payload.get("code") or e.get("error_code")
            break

    return {
        "roots": roots,
        "summary": {
            "total_events": len(events),
            "total_cost_usd": total_cost,
            "total_duration_ms": total_duration,
            "error_message": error_message,
            "error_type": error_type,
        },
    }


def _span_name(event: dict) -> str:
    t = event.get("type", "")
    if t == "llm.call":
        return f"llm.call:{event.get('llm_model', 'unknown')}"
    if t == "tool.invoke":
        return f"tool.{event.get('tool', 'unknown')}"
    if t == "handoff":
        return f"handoff:{event.get('payload', {}).get('from', '?')}->{event.get('payload', {}).get('to', '?')}"
    if t == "checkpoint":
        return f"checkpoint:step{event.get('payload', {}).get('step', 0)}"
    if t == "error":
        return f"error:{event.get('error_code', 'UNKNOWN')}"
    if t in ("run.start", "run.end", "step.start", "step.end"):
        return f"{t}:{event.get('agent', '?')}"
    return t


def _kind(event: dict) -> str:
    t = event.get("type", "")
    return {
        "llm.call": "llm",
        "tool.invoke": "tool",
        "handoff": "handoff",
        "checkpoint": "checkpoint",
        "error": "error",
        "run.start": "agent",
        "run.end": "agent",
        "step.start": "agent",
        "step.end": "agent",
    }.get(t, "agent")


def _status(event: dict) -> str:
    if event.get("error_code"):
        return "error"
    if event.get("type") == "error":
        return "error"
    return "ok"
