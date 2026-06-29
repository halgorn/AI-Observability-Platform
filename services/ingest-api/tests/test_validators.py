from __future__ import annotations

import pytest

from app.schemas import Event
from app.validators import validate_envelope, validate_payload


def test_envelope_accepts_valid():
    raw = {
        "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
        "span_id": "0aaa1bb0c0ffee01",
        "type": "llm.call",
        "started_at": "2026-06-29T12:00:00Z",
        "payload": {"model": "openai/gpt-4o-mini", "messages_hash": "sha256:" + "0" * 64, "messages_size": 1, "finish_reason": "stop"},
    }
    assert validate_envelope(raw) is None


def test_envelope_rejects_missing_payload():
    raw = {
        "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
        "span_id": "0aaa1bb0c0ffee01",
        "type": "llm.call",
        "started_at": "2026-06-29T12:00:00Z",
    }
    err = validate_envelope(raw)
    assert err is not None
    assert "payload" in err.message.lower()


def test_envelope_rejects_unknown_type():
    raw = {
        "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
        "span_id": "0aaa1bb0c0ffee01",
        "type": "made.up.type",
        "started_at": "2026-06-29T12:00:00Z",
        "payload": {},
    }
    err = validate_envelope(raw)
    assert err is not None


def test_payload_llm_call_requires_model():
    err = validate_payload("llm.call", {"messages_hash": "sha256:" + "0" * 64, "messages_size": 1, "finish_reason": "stop"})
    assert err is not None
    assert "model" in err.message.lower()


def test_payload_handoff_accepts_valid():
    p = {
        "from": "planner",
        "to": "executor",
        "reason": "delegation",
        "payload_hash": "sha256:" + "0" * 64,
    }
    assert validate_payload("handoff", p) is None


def test_payload_score_out_of_range():
    p = {
        "model": "openai/gpt-4o-mini",
        "dimension": "factuality",
        "score": 1.5,
    }
    err = validate_payload("judge.result", p)
    assert err is not None
