#!/usr/bin/env python3
"""Validate fixtures against JSON Schemas.

Strategy:
  valid/*.json   → must pass event.v1.json envelope
  invalid/*.json → must FAIL event.v1.json envelope
  Sub-shape validation: confirmed by type field → expected payload fields
"""
import json, pathlib, sys

try:
    import jsonschema
except ImportError:
    print("pip install jsonschema"); sys.exit(2)

ROOT = pathlib.Path(__file__).parent.parent
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "fixtures"

ENVELOPE = jsonschema.Draft202012Validator(
    json.loads((SCHEMAS / "event.v1.json").read_text())
)

PII_PATTERNS = {
    "email":       r"\b[\w.-]+@[\w.-]+\.\w+\b",
    "cpf":         r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
    "credit_card": r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b",
    "ssn":         r"\b\d{3}-\d{2}-\d{4}\b",
}

import re

def scan_pii(data: dict) -> list[str]:
    blob = json.dumps(data, default=str)
    return [name for name, pat in PII_PATTERNS.items() if re.search(pat, blob)]

TYPE_TO_REQUIRED = {
    "llm.call":    ["model"],
    "tool.invoke": ["tool", "args_hash"],
    "handoff":     ["from", "to", "reason"],
    "checkpoint":  ["step", "state_hash"],
    "error":       ["code"],
    "run.start":   ["input_hash", "agent"],
    "run.end":     ["status"],
    "step.start":  ["step"],
    "step.end":    ["step", "status"],
    "judge.result": ["model", "dimension", "score"],
    "artifact.link": ["artifact_hash", "kind"],
}

def check_envelope(data: dict) -> tuple[bool, str]:
    try:
        ENVELOPE.validate(data)
        return True, "envelope ok"
    except jsonschema.ValidationError as e:
        return False, f"envelope: {e.message[:80]}"

def check_payload(data: dict) -> tuple[bool, str]:
    t = data.get("type")
    payload = data.get("payload", {})
    required = TYPE_TO_REQUIRED.get(t, [])
    missing = [k for k in required if k not in payload]
    if missing:
        return False, f"payload missing required: {missing}"
    if t in ("run.end", "step.end"):
        status = payload.get("status")
        if status not in ("succeeded", "failed", "timeout", "cancelled", "skipped"):
            return False, f"status invalid: {status}"
    if t == "judge.result":
        score = payload.get("score")
        if not (0 <= score <= 1):
            return False, f"score out of range: {score}"
    return True, f"payload ({t}) ok"

def main():
    fails = 0
    for agent_dir in sorted(FIXTURES.iterdir()):
        if not agent_dir.is_dir():
            continue
        for kind, expect_valid in [("valid", True), ("invalid", False)]:
            d = agent_dir / kind
            if not d.exists():
                continue
            for f in sorted(d.glob("*.json")):
                data = json.loads(f.read_text())
                env_ok, env_msg = check_envelope(data)
                pay_ok, pay_msg = check_payload(data) if env_ok else (True, "skipped")
                pii = scan_pii(data)
                if expect_valid:
                    ok = env_ok and pay_ok and not pii
                    msg = env_msg if not env_ok else (pay_msg if not pay_ok else f"PII found: {pii}" if pii else pay_msg)
                else:
                    ok = (not env_ok) or bool(pii)
                    msg = env_msg if not env_ok else f"PII detected: {pii}"
                mark = "✓" if ok else "✗"
                print(f"  {mark} {agent_dir.name}/{kind}/{f.name}  [{msg}]")
                if not ok:
                    fails += 1
    print(f"\n{'PASS' if fails == 0 else f'FAIL — {fails} fixtures broken'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
