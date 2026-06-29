"""Langfuse exporter — sends events to Langfuse Cloud in parallel with our collector.

Set LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY (or LANGFUSE_HOST for self-host) and the
SDK will dual-export: our /v1/events + Langfuse spans.

No code changes for the user — just env vars.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

def _is_enabled_static() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


_ENABLED = _is_enabled_static()
_HOST = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

_client: Any = None
_lock = threading.Lock()


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        try:
            from langfuse import Langfuse
            _client = Langfuse(
                public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                host=_HOST,
            )
            return _client
        except ImportError:
            logger.warning("langfuse not installed; pip install langfuse")
            return None
        except Exception as e:
            logger.warning("failed to init Langfuse client: %s", e)
            return None


def is_enabled() -> bool:
    return _is_enabled_static()


def export_event(event: dict) -> None:
    """Send a single event to Langfuse as a trace+span.

    Maps our `Event` shape to Langfuse's:
      - run_id      → trace_id
      - span_id     → observation id
      - type=llm.call → 'generation'
      - type=tool.invoke → 'span' with kind=tool
      - type=handoff → 'span' with kind=handoff
      - other → 'span'
    """
    if not is_enabled():
        return
    client = _get_client()
    if client is None:
        return
    try:
        kind = _classify_kind(event)
        if kind == "generation":
            client.generation(
                id=event["span_id"],
                trace_id=event["run_id"],
                name=event.get("llm_model", "llm.call"),
                model=event.get("llm_model", "unknown/unknown"),
                input=event.get("payload", {}).get("messages_hash", ""),
                output=event.get("payload", {}).get("finish_reason", ""),
                usage={
                    "input": event.get("tokens_in") or 0,
                    "output": event.get("tokens_out") or 0,
                    "total": (event.get("tokens_in") or 0) + (event.get("tokens_out") or 0),
                },
                metadata={
                    "cost_usd": event.get("cost_usd"),
                    "duration_ms": event.get("duration_ms"),
                    "agent": event.get("agent"),
                    "tool": event.get("tool"),
                    "attributes": event.get("attributes", {}),
                },
                start_time=_to_dt(event.get("started_at")),
                end_time=_to_dt(event.get("ended_at")),
            )
        else:
            client.span(
                id=event["span_id"],
                trace_id=event["run_id"],
                name=f"{event.get('type', 'step')}.{event.get('agent') or event.get('tool') or 'unknown'}",
                input=event.get("payload", {}),
                output=event.get("attributes", {}),
                metadata={
                    "duration_ms": event.get("duration_ms"),
                    "agent": event.get("agent"),
                    "tool": event.get("tool"),
                    "error_code": event.get("error_code"),
                    "attributes": event.get("attributes", {}),
                },
                start_time=_to_dt(event.get("started_at")),
                end_time=_to_dt(event.get("ended_at")),
            )
        client.flush()
    except Exception as e:
        logger.warning("langfuse export failed: %s", e)


def _classify_kind(event: dict) -> str:
    t = event.get("type", "")
    if t == "llm.call":
        return "generation"
    return "span"


def _to_dt(ts: Any) -> Any:
    if ts is None:
        return None
    if hasattr(ts, "isoformat"):
        return ts
    try:
        from datetime import datetime, timezone
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    return None
