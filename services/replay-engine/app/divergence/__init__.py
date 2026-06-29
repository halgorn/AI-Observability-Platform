"""Divergence detection — compare replay output to original."""
from __future__ import annotations

from typing import Any, Optional


def check_divergence(
    *,
    original: dict,
    replayed: dict,
    kind: str,
) -> Optional[str]:
    """Returns None if matching, error string if diverged.

    `kind` is 'llm' or 'tool' — controls which fields to compare.
    """
    if kind == "llm":
        if original.get("model") != replayed.get("model"):
            return f"model mismatch: {original.get('model')} != {replayed.get('model')}"
        out_a = original.get("output") or original.get("messages_hash")
        out_b = replayed.get("output") or replayed.get("messages_hash")
        if out_a and out_b and out_a != out_b:
            return f"output hash mismatch: {out_a[:30]}... != {out_b[:30]}..."
    elif kind == "tool":
        if original.get("tool") != replayed.get("tool"):
            return f"tool mismatch: {original.get('tool')} != {replayed.get('tool')}"
        args_a = original.get("args_hash")
        args_b = replayed.get("args_hash")
        if args_a and args_b and args_a != args_b:
            return f"args hash mismatch: {args_a[:30]}... != {args_b[:30]}..."
    elif kind == "handoff":
        if original.get("from") != replayed.get("from"):
            return f"handoff.from mismatch"
        if original.get("to") != replayed.get("to"):
            return f"handoff.to mismatch"
    return None
