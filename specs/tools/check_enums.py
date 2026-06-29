#!/usr/bin/env python3
"""Verify that canonical enums in glossary match the JSON Schemas.

Catches drift between prose and code.
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).parent.parent
SCHEMAS = ROOT / "schemas"
GLOSSARY = ROOT / "00-glossary.md"


def extract_codeblock_list(md_text: str, header_prefix: str) -> list[str]:
    """Extract a code block that follows a line starting with header_prefix."""
    lines = md_text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(header_prefix):
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith("```"):
                    end = j
                    for k in range(j + 1, len(lines)):
                        if lines[k].strip().startswith("```"):
                            end = k
                            break
                    block = "\n".join(lines[j + 1:end])
                    return [x.strip() for x in block.split() if x.strip()]
                if lines[j].strip():
                    break
    return []


def extract_json_schema_enum(schema_path: pathlib.Path, ref: str) -> list[str]:
    """Resolve $ref and return enum array."""
    text = schema_path.read_text()
    schema = json.loads(text)
    if ref.startswith("#/"):
        parts = ref[2:].split("/")
        node = schema
        for p in parts:
            node = node.get(p, {})
        return node.get("enum", [])
    return []


glossary = GLOSSARY.read_text()
glossary_codes = set(extract_codeblock_list(glossary, "## Erros"))

event_schema = SCHEMAS / "event.v1.json"
schema_codes = set(extract_json_schema_enum(event_schema, "#/$defs/ErrorCode"))

missing_in_schema = glossary_codes - schema_codes
missing_in_glossary = schema_codes - glossary_codes

print(f"glossary has {len(glossary_codes)} codes, schema has {len(schema_codes)}")

if missing_in_schema:
    print(f"  In glossary but not in schema: {sorted(missing_in_schema)}")
if missing_in_glossary:
    print(f"  In schema but not in glossary: {sorted(missing_in_glossary)}")

if missing_in_schema or missing_in_glossary:
    sys.exit(1)
print("OK — enums in sync")
