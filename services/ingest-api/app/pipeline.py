from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .auth import ServiceToken, require_scope
from .errors import (
    IngestRejectedError, PiiDetectedError, RateLimitedError, SchemaInvalidError,
)
from .pii import redact, walk
from .ratelimit import RateLimiter
from .schemas import Event
from .validators import validate_envelope, validate_payload


class Store(Protocol):
    async def insert(self, event: dict) -> bool: ...


class Bus(Protocol):
    async def publish(self, topic: str, event: dict) -> None: ...
    async def publish_dlq(self, event: dict, error: dict) -> None: ...


@dataclass
class PipelineDeps:
    store: Store
    bus: Bus
    rate_limiter: RateLimiter
    pii_mode: str = "redact"  # 'strict' | 'redact' | 'passthrough'


@dataclass
class ProcessResult:
    accepted: int
    rejected: int
    details: list[dict[str, Any]]


def _process_one(
    raw: dict,
    org_id: str,
    deps: PipelineDeps,
) -> tuple[dict | None, dict | None]:
    """Returns (event_dict, error_dict). One is None."""
    err = validate_envelope(raw)
    if err is not None:
        return None, {
            "code": "SCHEMA_INVALID",
            "message": err.message[:200],
            "path": list(err.absolute_path),
        }

    try:
        event = Event.model_validate(raw)
    except Exception as e:
        return None, {"code": "SCHEMA_INVALID", "message": str(e)[:200]}

    if (pld_err := validate_payload(event.type, event.payload)) is not None:
        return None, {
            "code": "SCHEMA_INVALID",
            "message": f"payload invalid: {pld_err.message[:160]}",
            "path": list(pld_err.absolute_path),
        }

    pii_hits = walk({"payload": event.payload, "attributes": event.attributes})
    if pii_hits:
        if deps.pii_mode == "strict":
            return None, {"code": "PII_DETECTED", "kinds": pii_hits}
        if deps.pii_mode == "redact":
            event.payload = redact(event.payload)
            event.attributes = redact(event.attributes)

    event_dict = event.model_dump(mode="json")
    event_dict["org_id"] = org_id
    return event_dict, None


async def process_batch(
    events: list[dict],
    org_id: str,
    deps: PipelineDeps,
) -> ProcessResult:
    allowed, retry_after = deps.rate_limiter.check(org_id)
    if not allowed:
        raise RateLimitedError(retry_after)

    accepted = 0
    rejected = 0
    details: list[dict[str, Any]] = []

    for i, raw in enumerate(events):
        event_dict, err = _process_one(raw, org_id, deps)
        if err is not None:
            rejected += 1
            details.append({"index": i, **err})
            await deps.bus.publish_dlq(raw, err)
            continue

        inserted = await deps.store.insert(event_dict)
        if inserted:
            accepted += 1
            await deps.bus.publish("events.raw", event_dict)
        else:
            rejected += 1
            details.append({"index": i, "code": "INGEST_REJECTED", "message": "duplicate (run_id, span_id)"})

    return ProcessResult(accepted=accepted, rejected=rejected, details=details)
