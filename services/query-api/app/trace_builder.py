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
    error_span_id: str | None = None
    for e in events:
        if e.get("error_code") or e.get("type") == "error":
            attrs = e.get("attributes") or {}
            payload = e.get("payload") or {}
            error_message = attrs.get("error.message") or payload.get("message") or e.get("error_code")
            error_type = attrs.get("error.type") or payload.get("code") or e.get("error_code")
            error_span_id = e.get("span_id")
            break

    meta = _extract_run_meta(events)

    return {
        "roots": roots,
        "summary": {
            "total_events": len(events),
            "total_cost_usd": total_cost,
            "total_duration_ms": total_duration,
            "error_message": error_message,
            "error_type": error_type,
            "error_span_id": error_span_id,
            **meta,
        },
    }


def _extract_run_meta(events: list[dict]) -> dict:
    """Pull run-level metadata from run.start / run.end events.

    Also derives coverage flags (has_llm_calls, has_tool_invocations,
    has_messages, has_checkpoints) so the UI can explain a sparse trace.
    """
    meta: dict[str, Any] = {
        "input_hash": None,
        "input_size": None,
        "output_hash": None,
        "output_size": None,
        "prompt_version": None,
        "thread_id": None,
        "parent_run_id": None,
        "tags": [],
        "artifact_refs": [],
        "has_llm_calls": False,
        "has_tool_invocations": False,
        "has_messages": False,
        "has_checkpoints": False,
    }
    artifact_refs: set[str] = set()
    tags: set[str] = set()

    for ev in events:
        et = ev.get("type")
        attrs = ev.get("attributes") or {}
        payload = ev.get("payload") or {}

        if et == "run.start":
            meta["input_hash"] = payload.get("input_hash") or attrs.get("input_hash") or meta["input_hash"]
            meta["input_size"] = payload.get("input_size") or attrs.get("input_size") or meta["input_size"]
            meta["prompt_version"] = (
                payload.get("prompt_version") or attrs.get("prompt_version") or meta["prompt_version"]
            )
            meta["thread_id"] = payload.get("thread_id") or attrs.get("thread_id") or meta["thread_id"]
            meta["parent_run_id"] = (
                payload.get("parent_run_id") or attrs.get("parent_run_id") or meta["parent_run_id"]
            )
            for t in payload.get("tags") or attrs.get("tags") or []:
                if isinstance(t, str):
                    tags.add(t)
            ref = attrs.get("artifact_ref") or payload.get("artifact_ref")
            if isinstance(ref, str):
                artifact_refs.add(ref)

        elif et == "run.end":
            meta["output_hash"] = payload.get("output_hash") or attrs.get("output_hash") or meta["output_hash"]
            meta["output_size"] = payload.get("output_size") or attrs.get("output_size") or meta["output_size"]
            for t in payload.get("tags") or attrs.get("tags") or []:
                if isinstance(t, str):
                    tags.add(t)

        elif et == "llm.call":
            meta["has_llm_calls"] = True
            ref = attrs.get("artifact_ref") or payload.get("artifact_ref")
            if isinstance(ref, str):
                artifact_refs.add(ref)
            if payload.get("messages_hash") or attrs.get("artifact_ref"):
                meta["has_messages"] = True

        elif et == "tool.invoke":
            meta["has_tool_invocations"] = True
            ref = attrs.get("artifact_ref") or payload.get("artifact_ref")
            if isinstance(ref, str):
                artifact_refs.add(ref)

        elif et == "checkpoint":
            meta["has_checkpoints"] = True

        elif et == "artifact.link":
            ref = attrs.get("artifact_ref") or payload.get("artifact_ref")
            if isinstance(ref, str):
                artifact_refs.add(ref)

        for t in attrs.get("tags") or []:
            if isinstance(t, str):
                tags.add(t)

    meta["tags"] = sorted(tags)
    meta["artifact_refs"] = sorted(artifact_refs)
    return meta


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
