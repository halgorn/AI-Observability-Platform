"""UUIDv7 shim — uses uuid_extensions if available, fallback to uuid4."""
from __future__ import annotations
import uuid as _uuid

try:
    from uuid_extensions import uuid7  # type: ignore
except ImportError:
    def uuid7() -> _uuid.UUID:  # type: ignore
        return _uuid.uuid4()
