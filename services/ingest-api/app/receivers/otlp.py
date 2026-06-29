from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _hex_to_span_id(hex_str: str) -> str:
    return hex_str.zfill(16)[-16:]


def _ts_to_iso(ns: int) -> str:
    if not ns:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc).isoformat()


def _otlp_attrs_to_dict(attrs: list[dict]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kv in attrs:
        key = kv.get("key", "")
        value = kv.get("value", {})
        v = value.get("stringValue") or value.get("intValue") or value.get("doubleValue") or value.get("boolValue")
        if v is None and "arrayValue" in value:
            v = value["arrayValue"].get("values", [])
        if v is None and "kvlistValue" in value:
            v = value["kvlistValue"].get("values", [])
        out[key] = v
    return out


def _classify_event_type(name: str, attrs: dict) -> str:
    if "genai.llm.model" in attrs or name.startswith("llm."):
        return "llm.call"
    if "genai.tool.name" in attrs or name.startswith("tool."):
        return "tool.invoke"
    if "genai.handoff.to" in attrs or "handoff" in name:
        return "handoff"
    if "checkpoint" in name:
        return "checkpoint"
    if attrs.get("error.code") or name.endswith(".error"):
        return "error"
    if "judge" in name:
        return "judge.result"
    return "step.start"


def otlp_to_events(otlp_body: dict, org_id: str) -> list[dict]:
    """Translate OTLP HTTP requestExport → list of `Event` dicts.

    OTLP shape: { "resourceSpans": [ { "scopeSpans": [ { "spans": [...] } ] } ] }
    """
    events: list[dict] = []
    for rs in otlp_body.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                attrs = _otlp_attrs_to_dict(span.get("attributes", []))
                span_id = _hex_to_span_id(span.get("spanId", ""))
                parent = span.get("parentSpanId") or None
                if parent:
                    parent = _hex_to_span_id(parent)
                trace_id = span.get("traceId", "")
                run_id = attrs.get("genai.run.id") or trace_id

                event_type = _classify_event_type(span.get("name", ""), attrs)
                start_ns = int(span.get("startTimeUnixNano", 0))
                end_ns = int(span.get("endTimeUnixNano", 0))
                duration_ms = max(0, (end_ns - start_ns) // 1_000_000) if end_ns and start_ns else None

                payload: dict[str, Any] = {}
                if event_type == "llm.call":
                    payload = {
                        "model": attrs.get("genai.llm.model", "unknown/unknown"),
                        "messages_hash": "sha256:" + "0" * 64,
                        "messages_size": 0,
                        "finish_reason": "stop",
                    }
                elif event_type == "tool.invoke":
                    payload = {
                        "tool": attrs.get("genai.tool.name", "unknown"),
                        "args_hash": "sha256:" + "0" * 64,
                    }
                elif event_type == "handoff":
                    payload = {
                        "from": attrs.get("genai.handoff.from", ""),
                        "to": attrs.get("genai.handoff.to", ""),
                        "reason": "delegation",
                        "payload_hash": "sha256:" + "0" * 64,
                    }
                elif event_type == "checkpoint":
                    payload = {
                        "step": 0,
                        "state_hash": "sha256:" + "0" * 64,
                    }
                elif event_type == "error":
                    payload = {
                        "code": attrs.get("error.code", "UNKNOWN"),
                        "message": span.get("status", {}).get("message", "unknown"),
                    }

                event = {
                    "run_id": run_id,
                    "parent_span_id": parent,
                    "span_id": span_id,
                    "type": event_type,
                    "agent": attrs.get("genai.agent.name"),
                    "tool": attrs.get("genai.tool.name"),
                    "llm_model": attrs.get("genai.llm.model"),
                    "started_at": _ts_to_iso(start_ns),
                    "ended_at": _ts_to_iso(end_ns) if end_ns else None,
                    "duration_ms": duration_ms,
                    "tokens_in": attrs.get("genai.llm.tokens.input"),
                    "tokens_out": attrs.get("genai.llm.tokens.output"),
                    "cost_usd": attrs.get("genai.llm.cost.usd"),
                    "error_code": attrs.get("error.code"),
                    "payload": payload,
                    "attributes": attrs,
                }
                events.append(event)
    return events
