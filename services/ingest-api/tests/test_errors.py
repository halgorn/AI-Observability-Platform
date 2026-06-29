from __future__ import annotations

import pytest

from app.errors import (
    AuthForbiddenError, AuthMissingError, IngestRejectedError,
    PiiDetectedError, RateLimitedError, SchemaInvalidError,
)


def test_schema_invalid_error_shape():
    e = SchemaInvalidError("missing field", {"field": "payload"})
    body = e.to_dict("req_123")
    assert body["error"]["code"] == "SCHEMA_INVALID"
    assert body["error"]["request_id"] == "req_123"
    assert body["error"]["details"]["field"] == "payload"


def test_ingest_rejected_default_status():
    assert IngestRejectedError("dup").status == 400
    assert IngestRejectedError("dup").code == "INGEST_REJECTED"


def test_pii_detected_carries_kinds():
    e = PiiDetectedError(["email", "cpf"])
    body = e.to_dict("req")
    assert body["error"]["code"] == "PII_DETECTED"
    assert body["error"]["details"]["kinds"] == ["email", "cpf"]


def test_auth_missing_status():
    assert AuthMissingError().status == 401


def test_auth_forbidden_message():
    e = AuthForbiddenError("token expired")
    body = e.to_dict("req")
    assert body["error"]["code"] == "AUTH_FORBIDDEN"
    assert "expired" in body["error"]["message"]


def test_rate_limited_includes_retry_after():
    e = RateLimitedError(retry_after_s=42)
    body = e.to_dict("req")
    assert body["error"]["details"]["retry_after_s"] == 42
    assert e.status == 429
