"""Convert canonical JSON Schema (Draft 2020-12) to a flat dict accepted by
Gemini / OpenAI structured-output APIs.

Strips:
  - $ref     (inlined recursively against the root schema)
  - $schema  (unsupported by structured-output endpoints)
  - $id      (unsupported)
  - uniqueItems (unsupported)
  - additionalProperties (ONLY when value is literally False — preserves
    schema-valued additionalProperties such as {"type": "string"})

Preserves: type, properties, required, items, enum, const, description,
format, minimum, maximum, pattern, and every other keyword.

Pure function. No I/O. Does not mutate input (deepcopy at entry).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

__all__ = ["to_api_schema", "SchemaAdapterError"]

_STRIP_UNCONDITIONAL = {"$schema", "$id", "uniqueItems"}


class SchemaAdapterError(ValueError):
    """Raised when a $ref pointer cannot be resolved within the schema root."""


def to_api_schema(canonical: dict) -> dict:
    """Return a flat, API-safe copy of `canonical`.

    The input is deep-copied so the caller's dict is never mutated. The
    returned dict is a fresh structure containing only keywords Gemini and
    OpenAI structured-output endpoints accept.

    Raises SchemaAdapterError if an internal $ref cannot be resolved.
    """
    root = deepcopy(canonical)
    return _walk(root, root)


def _walk(node: Any, root: dict) -> Any:
    if isinstance(node, dict):
        # Pure-ref node (e.g., {"$ref": "#/definitions/Foo"}) — inline then recurse.
        # We only treat a node as a pure ref when $ref is its only key; if it has
        # siblings, inlining is ambiguous — per JSON Schema, siblings of $ref are
        # ignored in older drafts, but Draft 2020-12 allows them. We take the
        # conservative path: only inline pure-$ref nodes; otherwise drop the $ref
        # and keep the siblings.
        if "$ref" in node and len(node) == 1:
            resolved = _resolve_ref(node["$ref"], root)
            return _walk(deepcopy(resolved), root)

        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in _STRIP_UNCONDITIONAL:
                continue
            if k == "$ref":
                # Mixed $ref + siblings: conservatively drop the $ref and keep siblings.
                # (Keeping $ref would leak it into the API call.)
                continue
            if k == "additionalProperties" and v is False:
                continue
            if k == "definitions" or k == "$defs":
                # These exist only to host $ref targets. We've already inlined
                # all refs via recursion; drop the ref-target pools.
                continue
            out[k] = _walk(v, root)
        return out

    if isinstance(node, list):
        return [_walk(x, root) for x in node]

    return node


def _resolve_ref(ref: str, root: dict) -> dict:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise SchemaAdapterError(
            f"Only internal JSON-pointer refs are supported (got {ref!r})"
        )
    node: Any = root
    # "#/foo/bar" -> ["foo", "bar"]; handle RFC-6901 escapes ~1->/ ~0->~
    for part in ref.lstrip("#/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaAdapterError(f"Unresolvable $ref: {ref!r}")
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaAdapterError(f"$ref {ref!r} does not point to a schema object")
    return node
