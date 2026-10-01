from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]


class StudioError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise StudioError("Expected a portable relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or PureWindowsPath(value).drive or any(x in ("..", ".", "") for x in value.split("/")):
        raise StudioError("Path must stay within its root")
    if any(x.endswith((".", " ")) or x.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1,10)], *[f"LPT{i}" for i in range(1,10)]} for x in p.parts):
        raise StudioError("Nonportable path")
    return value


def inside(root, value, must_exist=True):
    root = Path(root).resolve(strict=True)
    p = root / relative(value)
    cursor = p
    while cursor != root:
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise StudioError("Symlink/junction paths are not allowed")
        cursor = cursor.parent
    resolved = p.resolve(strict=must_exist)
    if not resolved.is_relative_to(root):
        raise StudioError("Path escapes project root")
    return resolved


def ident(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", value) or len(value) > 100:
        raise StudioError("Invalid stable identifier")
    return value


def validate(value, schema, location="$"):
    """Validate the deliberately small JSON Schema vocabulary used by this package.

    No remote refs or arbitrary schema execution. External schemas should use a
    full Draft 2020-12 implementation; these schemas are also independently tested.
    """
    if schema is True:
        return
    if schema is False:
        raise StudioError(f"{location}: forbidden value")
    allowed = {"$schema", "$id", "title", "description", "type", "properties", "required", "additionalProperties", "items", "minItems", "maxItems", "uniqueItems", "minLength", "maxLength", "pattern", "minimum", "maximum", "enum", "const", "anyOf", "default"}
    unknown = set(schema) - allowed
    if unknown:
        raise StudioError(f"Unsupported schema keywords: {sorted(unknown)}")
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            try:
                validate(value, branch, location)
                break
            except StudioError:
                pass
        else:
            raise StudioError(f"{location}: no matching schema branch")
    types = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list), "string": lambda v: isinstance(v, str), "boolean": lambda v: type(v) is bool, "integer": lambda v: type(v) is int, "number": lambda v: type(v) in (int, float) and math.isfinite(v), "null": lambda v: v is None}
    expected = schema.get("type")
    if expected and not any(types[t](value) for t in ([expected] if isinstance(expected, str) else expected)):
        raise StudioError(f"{location}: expected {expected}")
    if "enum" in schema and canonical(value) not in [canonical(v) for v in schema["enum"]]:
        raise StudioError(f"{location}: invalid choice {value!r}")
    if "const" in schema and canonical(value) != canonical(schema["const"]):
        raise StudioError(f"{location}: unexpected constant")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            raise StudioError(f"{location}: missing {sorted(missing)}")
        for key, item in value.items():
            child = schema.get("properties", {}).get(key, schema.get("additionalProperties", True))
            validate(item, child, f"{location}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise StudioError(f"{location}: invalid item count")
        if schema.get("uniqueItems") and len({canonical(v) for v in value}) != len(value):
            raise StudioError(f"{location}: duplicate items")
        for i, item in enumerate(value):
            validate(item, schema.get("items", True), f"{location}[{i}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            raise StudioError(f"{location}: invalid string length")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise StudioError(f"{location}: invalid string format")
    if type(value) in (int, float) and not (schema.get("minimum", -float("inf")) <= value <= schema.get("maximum", float("inf"))):
        raise StudioError(f"{location}: outside bounds")


def contract(name, value):
    validate(value, read_json(ROOT / "schemas" / f"{name}.schema.json"))
    return value


def route(component):
    contract("component", component)
    f = component["features"]
    sheet = f.get("sheet_like", False) or f.get("sewn", False)
    solid = f.get("rigid", False) or f.get("articulated", False)
    uncertain = f.get("hidden_structure", False) or sheet == solid
    selected = None if uncertain else ("PATTERN_SEWN" if sheet else "MULTIVIEW_PART")
    return {"decision_type": "pipeline_route", "subject": component["id"], "selected": selected,
            "confidence": "low" if uncertain else "high", "evidence": component["evidence"],
            "reasons": [k for k, v in f.items() if v], "alternatives": [r for r in ("PATTERN_SEWN", "MULTIVIEW_PART") if r != selected],
            "requires_human": uncertain or not component["evidence"]}
