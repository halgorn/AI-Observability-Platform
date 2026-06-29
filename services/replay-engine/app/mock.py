"""Mock layer for deterministic replay.

When mock_llm=True, LLM calls return cached responses from `originals` map.
When mock_tools contains a tool name, that tool returns cached args_hash → result_hash.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MockLayer:
    def __init__(self, *, mock_llm: bool = True, mock_tools: Optional[set[str]] = None) -> None:
        self.mock_llm = mock_llm
        self.mock_tools = set(mock_tools or [])
        self.llm_responses: dict[str, dict] = {}
        self.tool_responses: dict[str, dict] = {}

    def register_llm(self, model: str, input_hash: str, response: dict) -> None:
        self.llm_responses[f"{model}:{input_hash}"] = response

    def register_tool(self, tool: str, args_hash: str, result: Any) -> None:
        self.tool_responses[f"{tool}:{args_hash}"] = result

    def call_llm(self, *, model: str, messages: list, **kwargs) -> dict:
        if not self.mock_llm:
            raise RuntimeError("mock_llm=False: real LLM call not supported in replay")
        messages_hash = _hash_obj(messages)
        key = f"{model}:{messages_hash}"
        if key in self.llm_responses:
            return self.llm_responses[key]
        return {
            "model": model,
            "output": "[MOCK_NO_RESPONSE]",
            "tokens_in": sum(len(str(m)) for m in messages) // 4,
            "tokens_out": 10,
            "cost_usd": 0.0,
            "cached": True,
        }

    def call_tool(self, *, tool: str, args: dict) -> Any:
        if tool not in self.mock_tools:
            raise RuntimeError(f"tool {tool!r} not in mock_tools={self.mock_tools}")
        args_hash = _hash_obj(args)
        key = f"{tool}:{args_hash}"
        if key in self.tool_responses:
            return self.tool_responses[key]
        return {"_mocked": True, "tool": tool, "args_hash": args_hash}


def _hash_obj(obj: Any) -> str:
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items() if v is not None}
        if isinstance(o, list):
            return [_clean(x) for x in o]
        return o
    blob = json.dumps(_clean(obj), sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()
