"""PII detection + redaction.

Mirrors specs/domains/14-data-governance.md §PII.
"""
from __future__ import annotations

import re
from typing import Any

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email":       re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b"),
    "cpf":         re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "cnpj":        re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    "credit_card": re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
    "ssn":         re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone_br":    re.compile(r"\b\+?55?\s?\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b"),
    "ip_public":   re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

REDACTION_TEMPLATES = {
    "email":       "[REDACTED:email]",
    "cpf":         "[REDACTED:cpf]",
    "cnpj":        "[REDACTED:cnpj]",
    "credit_card": "[REDACTED:card]",
    "ssn":         "[REDACTED:ssn]",
    "phone_br":    "[REDACTED:phone]",
    "ip_public":   "[REDACTED:ip]",
}


def scan_pii(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    return [name for name, pat in PII_PATTERNS.items() if pat.search(value)]


def redact_str(value: str) -> str:
    out = value
    for name, pat in PII_PATTERNS.items():
        out = pat.sub(REDACTION_TEMPLATES[name], out)
    return out


def redact_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_str(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    return obj
