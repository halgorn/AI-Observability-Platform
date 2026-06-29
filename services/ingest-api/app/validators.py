from __future__ import annotations

import json
import os
import pathlib

import jsonschema


def _resolve_spec_root() -> pathlib.Path:
    env = os.environ.get("SPEC_ROOT")
    if env:
        return pathlib.Path(env) / "schemas"
    return pathlib.Path(__file__).resolve().parents[3] / "specs" / "schemas"


SPEC_ROOT = _resolve_spec_root()

_ENVELOPE_SCHEMA = json.loads((SPEC_ROOT / "event.v1.json").read_text())
_PAYLOAD_SCHEMA = json.loads((SPEC_ROOT / "event-types.v1.json").read_text())

_ENVELOPE_VALIDATOR = jsonschema.Draft202012Validator(_ENVELOPE_SCHEMA)


_PAYLOAD_VALIDATORS: dict[str, jsonschema.Draft202012Validator] = {}
_TYPE_TO_DEFINITION: dict[str, str] = {}


def _build_payload_validators() -> None:
    import re
    for entry in _PAYLOAD_SCHEMA["oneOf"]:
        ref = entry.get("$ref", "")
        if not ref:
            continue
        name = ref.rsplit("/", 1)[-1]
        defn = _PAYLOAD_SCHEMA["$defs"][name]
        _PAYLOAD_VALIDATORS[name] = jsonschema.Draft202012Validator(defn)
        snake = re.sub(r"(?<!^)(?=[A-Z])", ".", name).lower()
        _TYPE_TO_DEFINITION[snake] = name


_build_payload_validators()


def validate_envelope(data: dict) -> jsonschema.ValidationError | None:
    errors = list(_ENVELOPE_VALIDATOR.iter_errors(data))
    return errors[0] if errors else None


def validate_payload(event_type: str, payload: dict) -> jsonschema.ValidationError | None:
    defn_name = _TYPE_TO_DEFINITION.get(event_type)
    if defn_name is None:
        return jsonschema.ValidationError(f"unknown event type: {event_type}")
    errors = list(_PAYLOAD_VALIDATORS[defn_name].iter_errors(payload))
    return errors[0] if errors else None
