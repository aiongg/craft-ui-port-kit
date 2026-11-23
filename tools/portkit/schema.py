"""The JSON schema check of the kit: the subset of JSON Schema the kit's schemas use (type, required, properties,
additionalProperties false, enum, items, minItems, minLength, pattern). swarm.py checks agent results with it, and
the plan scripts check the files agents write with the same function, so one schema means the same everywhere."""
from __future__ import annotations

import json
import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def load(name: str) -> dict:
    """A schema file of templates/, parsed."""
    return json.loads((TEMPLATES / name).read_text())


def schema_errors(v, s: dict, path: str = "$", out: list | None = None) -> list[str]:
    out = [] if out is None else out
    if len(out) >= 20 or not isinstance(s, dict):
        return out
    t = s.get("type")
    types = t if isinstance(t, list) else ([t] if t else [])
    ok = {"object": lambda x: isinstance(x, dict), "array": lambda x: isinstance(x, list),
          "string": lambda x: isinstance(x, str), "boolean": lambda x: isinstance(x, bool),
          "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
          "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool), "null": lambda x: x is None}
    if types and not any(ok.get(ty, lambda x: True)(v) for ty in types):
        out.append(f"{path}: expected {'/'.join(types)}, got {type(v).__name__}")
        return out
    if "enum" in s and v not in s["enum"]:
        out.append(f"{path}: {v!r} is not one of {s['enum']}")
    if isinstance(v, str):
        if len(v) < s.get("minLength", 0):
            out.append(f"{path}: shorter than {s['minLength']} characters")
        if "pattern" in s and not re.search(s["pattern"], v):
            out.append(f"{path}: {v!r} does not match {s['pattern']}")
    if isinstance(v, dict):
        for k in s.get("required", []):
            if k not in v:
                out.append(f"{path}: missing key {k!r}")
        props = s.get("properties", {})
        for k, sub in props.items():
            if k in v:
                schema_errors(v[k], sub, f"{path}.{k}", out)
        if s.get("additionalProperties") is False:
            for k in v:
                if k not in props:
                    out.append(f"{path}: unexpected key {k!r}")
    if isinstance(v, list):
        if len(v) < s.get("minItems", 0):
            out.append(f"{path}: fewer than {s['minItems']} items")
        if isinstance(s.get("items"), dict):
            for i, x in enumerate(v):
                schema_errors(x, s["items"], f"{path}[{i}]", out)
    return out
