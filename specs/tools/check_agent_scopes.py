#!/usr/bin/env python3
"""Validate that agent cards only reference domains that exist."""
import re, pathlib, sys

ROOT = pathlib.Path(__file__).parent.parent
AGENTS = ROOT / "agents"
DOMAINS = ROOT / "domains"
SCHEMAS = ROOT / "schemas"

existing = {
    p.name
    for p in DOMAINS.glob("*.md")
} | {
    p.name
    for p in SCHEMAS.glob("*.json")
} | {
    "00-glossary.md", "01-naming-conventions.md", "02-event-schema.md", "README.md",
}

DOMAIN_REF = re.compile(r"`((?:\d{2}-)?[a-z][\w./-]*\.md)`")
errors = 0

for card in sorted(AGENTS.glob("*-agent.md")):
    text = card.read_text()
    for ref in set(DOMAIN_REF.findall(text)):
        if ref not in existing:
            print(f"{card.name}  → `{ref}`  NOT FOUND")
            errors += 1

print(f"\n{errors} broken domain refs" if errors else "\nAll agent refs valid")
sys.exit(1 if errors else 0)
