"""
Sprint 0a — generate TypeScript types from Pydantic response models
====================================================================
Reads `backend.schemas.RESPONSE_MODELS`, walks every Pydantic model that
appears (directly or transitively), and writes `frontend/src/lib/api-types.ts`.

Run after editing any model in backend/schemas/__init__.py:

    python scripts/generate_ts_types.py

The output file is regenerated wholesale. Never hand-edit it.

Strategy
--------
We use Pydantic's JSON schema as the input (instead of poking at type hints
directly) because v2 has already done all the recursion, list/dict resolution,
and Optional/Union handling we'd otherwise have to reimplement. We then walk
`$defs` once and emit one TypeScript `interface` per model.

This keeps the codegen small (~150 LOC) and lets the schema grow without
codegen changes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE    = Path(__file__).resolve().parent
_ROOT    = _HERE.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from schemas import RESPONSE_MODELS  # noqa: E402

OUT_PATH = _ROOT / "frontend" / "src" / "lib" / "api-types.ts"


# ─────────────────────────────────────────────────────────────────────────────
# JSON Schema → TypeScript type-string
# ─────────────────────────────────────────────────────────────────────────────
def _ref_name(ref: str) -> str:
    """'#/$defs/PriceQuote' -> 'PriceQuote'."""
    return ref.split("/")[-1]


def ts_type(schema: dict) -> str:
    """Render a JSON-schema fragment as a TypeScript type expression."""
    if not schema:
        return "unknown"

    # $ref
    if "$ref" in schema:
        return _ref_name(schema["$ref"])

    # anyOf / oneOf — used heavily by Pydantic v2 for Optional[...]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            parts = [ts_type(s) for s in schema[key]]
            # Pydantic spells Optional as anyOf[..., {"type":"null"}]; collapse
            # `null` into `| null`.
            parts = sorted(set(parts), key=lambda s: s == "null")
            return " | ".join(parts) if parts else "unknown"

    # allOf — Pydantic uses this for nullable refs in some shapes
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return ts_type(schema["allOf"][0])

    t = schema.get("type")
    if isinstance(t, list):
        # union of types
        return " | ".join(ts_type({"type": x}) for x in t)

    if t == "string":
        if "enum" in schema:
            return " | ".join(json.dumps(v) for v in schema["enum"])
        return "string"
    if t in ("integer", "number"):
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "null":
        return "null"
    if t == "array":
        item = schema.get("items", {})
        return f"Array<{ts_type(item)}>"
    if t == "object":
        ap = schema.get("additionalProperties")
        if isinstance(ap, dict):
            return f"Record<string, {ts_type(ap)}>"
        if ap is True or ap is None:
            return "Record<string, unknown>"
        # fallback: inline object
        props = schema.get("properties") or {}
        req   = set(schema.get("required") or [])
        if props:
            inner = "; ".join(
                f"{json.dumps(k)}{'' if k in req else '?'}: {ts_type(v)}"
                for k, v in props.items()
            )
            return f"{{ {inner} }}"
        return "Record<string, unknown>"

    # No type info — most permissive
    return "unknown"


def render_interface(name: str, schema: dict) -> str:
    props = schema.get("properties") or {}
    req   = set(schema.get("required") or [])
    if not props:
        return f"export interface {name} {{ [key: string]: unknown; }}\n"

    lines = [f"export interface {name} {{"]
    for prop, sub in props.items():
        ts = ts_type(sub)
        optional = "" if prop in req else "?"
        # Quote keys that aren't plain identifiers
        key = prop if prop.isidentifier() else json.dumps(prop)
        lines.append(f"  {key}{optional}: {ts};")
    # Pydantic models inherit extra="allow"; reflect that on the TS side so
    # consumers can read undocumented fields without compiler complaints.
    lines.append("  [key: string]: unknown;")
    lines.append("}")
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Build the output
# ─────────────────────────────────────────────────────────────────────────────
def collect_schemas() -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Returns (top_level_models, defs):
      top_level_models: {ModelName: schema} for each entry in RESPONSE_MODELS
      defs:             {Name: schema} for every transitively referenced model
    """
    top: dict[str, dict] = {}
    defs: dict[str, dict] = {}
    for model in RESPONSE_MODELS.values():
        s = model.model_json_schema(ref_template="#/$defs/{model}")
        # In Pydantic v2 the root schema is the model itself; nested ones go
        # under "$defs".
        name = s.get("title") or model.__name__
        # Strip out $defs before storing the top-level body so we don't double
        # emit.
        nested = s.pop("$defs", {})
        top[name] = s
        for k, v in nested.items():
            defs.setdefault(k, v)
    return top, defs


def generate() -> str:
    top, defs = collect_schemas()

    header = (
        "/**\n"
        " * AUTO-GENERATED — do not edit by hand.\n"
        " * Source: backend/schemas/__init__.py\n"
        " * Regenerate: `python scripts/generate_ts_types.py`\n"
        " *\n"
        " * These types describe PULSE backend responses. Models use Pydantic\n"
        " * `extra=\"allow\"`, so every interface ends with an index signature\n"
        " * permitting unknown fields — undocumented payload extensions stay\n"
        " * accessible without breaking the type check.\n"
        " */\n\n"
    )

    parts: list[str] = [header]

    # 1) Nested definitions (sorted for stable diffs)
    if defs:
        parts.append("// ── Nested models ──────────────────────────────────────\n")
        for name in sorted(defs):
            parts.append(render_interface(name, defs[name]))
            parts.append("\n")

    # 2) Top-level response models
    parts.append("// ── Top-level responses ────────────────────────────────\n")
    for name in sorted(top):
        parts.append(render_interface(name, top[name]))
        parts.append("\n")

    # 3) Endpoint → response-type map (string literal, so consumers can ref it)
    parts.append("// ── Endpoint → response type ───────────────────────────\n")
    parts.append("export interface ApiResponseMap {\n")
    for path, model in sorted(RESPONSE_MODELS.items()):
        parts.append(f'  {json.dumps(path)}: {model.__name__};\n')
    parts.append("}\n")

    return "".join(parts)


def main() -> int:
    out = generate()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(out, encoding="utf-8")
    print(f"wrote {OUT_PATH}  ({len(out):,} bytes, "
          f"{out.count('export interface')} interfaces)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
