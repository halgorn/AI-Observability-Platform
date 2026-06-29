from __future__ import annotations

import re

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email":       re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b"),
    "cpf":         re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "cnpj":        re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    "credit_card": re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
    "ssn":         re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone_br":    re.compile(r"\b\+?55?\s?\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b"),
    "ip_public":   re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

PII_SCAN_TARGETS = ("payload", "attributes", "message", "tool_args", "tool_result", "input", "output")

REDACTION_TEMPLATES = {
    "email":       "[REDACTED:email]",
    "cpf":         "[REDACTED:cpf]",
    "cnpj":        "[REDACTED:cnpj]",
    "credit_card": "[REDACTED:card]",
    "ssn":         "[REDACTED:ssn]",
    "phone_br":    "[REDACTED:phone]",
    "ip_public":   "[REDACTED:ip]",
}


def scan(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    return [name for name, pat in PII_PATTERNS.items() if pat.search(value)]


def walk(obj: object) -> list[str]:
    hits: list[str] = []
    if isinstance(obj, str):
        hits.extend(scan(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in PII_SCAN_TARGETS or k.startswith("pii."):
                hits.extend(scan(str(v)) if isinstance(v, (str, int, float)) else walk(v))
            else:
                hits.extend(walk(v))
    elif isinstance(obj, list):
        for item in obj:
            hits.extend(walk(item))
    return list(dict.fromkeys(hits))


def redact_str(value: str) -> str:
    out = value
    for name, pat in PII_PATTERNS.items():
        out = pat.sub(REDACTION_TEMPLATES[name], out)
    return out


def redact(obj: object) -> object:
    if isinstance(obj, str):
        return redact_str(obj)
    if isinstance(obj, dict):
        return {k: (redact_str(v) if k in PII_SCAN_TARGETS and isinstance(v, str) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(item) for item in obj]
    return obj
