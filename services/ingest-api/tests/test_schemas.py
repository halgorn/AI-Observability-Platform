from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import Event, LlmCallPayload, RunStartPayload


def test_valid_event_parses():
    e = Event.model_validate({
        "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
        "span_id": "0aaa1bb0c0ffee01",
        "type": "llm.call",
        "agent": "planner",
        "llm_model": "openai/gpt-4o-mini",
        "started_at": "2026-06-29T12:00:00.000Z",
        "ended_at": "2026-06-29T12:00:01.000Z",
        "payload": {
            "model": "openai/gpt-4o-mini",
            "messages_hash": "sha256:" + "0" * 64,
            "messages_size": 100,
            "finish_reason": "stop",
        },
        "attributes": {},
    })
    assert e.type == "llm.call"
    assert e.duration_ms is None


def test_invalid_span_id_rejected():
    with pytest.raises(ValidationError):
        Event.model_validate({
            "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
            "span_id": "tooshort",
            "type": "llm.call",
            "started_at": "2026-06-29T12:00:00Z",
            "payload": {},
        })


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        Event.model_validate({
            "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
            "span_id": "0aaa1bb0c0ffee01",
            "type": "llm.call",
            "started_at": "2026-06-29T12:00:00Z",
            "payload": {"model": "openai/gpt-4o-mini", "messages_hash": "sha256:" + "0" * 64, "messages_size": 1, "finish_reason": "stop"},
            "attributes": {},
            "unknown_field": "x",
        })


def test_ended_before_started_rejected():
    with pytest.raises(ValidationError, match="ended_at"):
        Event.model_validate({
            "run_id": "019065a1-7c8e-7abc-9def-1234567890ab",
            "span_id": "0aaa1bb0c0ffee01",
            "type": "llm.call",
            "started_at": "2026-06-29T12:00:00Z",
            "ended_at": "2026-06-29T11:00:00Z",
            "payload": {},
        })


def test_llm_call_payload_subshape():
    p = LlmCallPayload.model_validate({
        "model": "openai/gpt-4o-mini",
        "messages_hash": "sha256:" + "0" * 64,
        "messages_size": 100,
        "finish_reason": "stop",
    })
    assert p.model == "openai/gpt-4o-mini"


def test_run_start_payload_requires_agent():
    with pytest.raises(ValidationError):
        RunStartPayload.model_validate({
            "input_hash": "sha256:" + "0" * 64,
        })
