#!/usr/bin/env python3
"""Validate that all JSON Schemas in specs/schemas/ parse and are valid Draft 2020-12."""
import json, pathlib, sys

try:
    import jsonschema
except ImportError:
    print("pip install jsonschema")
    sys.exit(2)

SCHEMAS = pathlib.Path(__file__).parent.parent / "schemas"
errors = 0

for path in sorted(SCHEMAS.glob("*.json")):
    try:
        schema = json.loads(path.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        print(f"{path.name}  OK")
    except Exception as e:
        print(f"{path.name}  FAIL: {e}")
        errors += 1

sys.exit(1 if errors else 0)
