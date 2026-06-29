from __future__ import annotations

from typing import Any


class IngestError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}

    def to_dict(self, request_id: str) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "request_id": request_id,
                **({"details": self.details} if self.details else {}),
            }
        }


class SchemaInvalidError(IngestError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("SCHEMA_INVALID", message, 400, details)


class IngestRejectedError(IngestError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("INGEST_REJECTED", message, 400, details)


class PiiDetectedError(IngestError):
    def __init__(self, kinds: list[str]) -> None:
        super().__init__("PII_DETECTED", f"PII detected: {','.join(kinds)}", 400, {"kinds": kinds})


class AuthMissingError(IngestError):
    def __init__(self) -> None:
        super().__init__("AUTH_MISSING", "Authorization header required", 401)


class AuthForbiddenError(IngestError):
    def __init__(self, message: str) -> None:
        super().__init__("AUTH_FORBIDDEN", message, 403)


class RateLimitedError(IngestError):
    def __init__(self, retry_after_s: int) -> None:
        super().__init__("RATE_LIMITED", f"rate limit exceeded, retry in {retry_after_s}s", 429, {"retry_after_s": retry_after_s})


class InternalError(IngestError):
    def __init__(self, message: str = "internal server error") -> None:
        super().__init__("INTERNAL_ERROR", message, 500)


class DependencyDownError(IngestError):
    def __init__(self, dep: str) -> None:
        super().__init__("DEPENDENCY_DOWN", f"dependency unavailable: {dep}", 503, {"dependency": dep})
