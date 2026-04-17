"""Unit tests for lib.schema_adapter — canonical -> API-safe JSON Schema.

Verifies:
  - Unconditional strips: $schema, $id, uniqueItems
  - Conditional strip: additionalProperties (only when value is literally False)
  - $ref inlining with internal JSON pointers (#/definitions/X, #/$defs/X)
  - Error on unresolvable / external $ref
  - Idempotency and non-mutation
  - Preservation of: type, properties, required, items, enum, const, description
  - Real-schema round-trip on the Plan 01 canonical video_analysis schema.

All tests run in <1 second with no network, no API keys, no fixtures on disk.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.schema_adapter import to_api_schema, SchemaAdapterError  # noqa: E402


class TestSchemaAdapter:
    def test_strips_schema_and_id(self):
        inp = {"$schema": "https://json-schema.org/draft/2020-12/schema",
               "$id": "openmontage/test",
               "type": "object"}
        out = to_api_schema(inp)
        assert "$schema" not in out
        assert "$id" not in out
        assert out["type"] == "object"

    def test_strips_additional_properties_false(self):
        out = to_api_schema({"type": "object", "additionalProperties": False})
        assert "additionalProperties" not in out

    def test_keeps_additional_properties_object(self):
        out = to_api_schema({
            "type": "object",
            "additionalProperties": {"type": "string", "enum": ["low", "medium", "high"]},
        })
        assert out["additionalProperties"] == {"type": "string", "enum": ["low", "medium", "high"]}

    def test_strips_unique_items(self):
        out = to_api_schema({"type": "array", "items": {"type": "integer"}, "uniqueItems": True})
        assert "uniqueItems" not in out
        assert out["items"] == {"type": "integer"}

    def test_nested_strip(self):
        out = to_api_schema({
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                "meta": {"type": "object", "additionalProperties": False, "$id": "nested"},
            },
        })
        assert "uniqueItems" not in out["properties"]["tags"]
        assert "additionalProperties" not in out["properties"]["meta"]
        assert "$id" not in out["properties"]["meta"]

    def test_inlines_internal_ref(self):
        inp = {
            "type": "object",
            "properties": {"foo": {"$ref": "#/definitions/Foo"}},
            "definitions": {"Foo": {"type": "integer", "minimum": 0}},
        }
        out = to_api_schema(inp)
        assert out["properties"]["foo"] == {"type": "integer", "minimum": 0}
        assert "$ref" not in json.dumps(out)

    def test_inlines_defs_variant(self):
        inp = {
            "type": "object",
            "properties": {"bar": {"$ref": "#/$defs/Bar"}},
            "$defs": {"Bar": {"type": "string"}},
        }
        out = to_api_schema(inp)
        assert out["properties"]["bar"] == {"type": "string"}

    def test_drops_definitions_pool_after_inline(self):
        inp = {
            "type": "object",
            "properties": {"foo": {"$ref": "#/definitions/Foo"}},
            "definitions": {"Foo": {"type": "integer"}},
        }
        out = to_api_schema(inp)
        assert "definitions" not in out
        assert "$defs" not in out

    def test_raises_on_unresolvable_ref(self):
        inp = {"properties": {"x": {"$ref": "#/definitions/Missing"}}, "definitions": {}}
        with pytest.raises(SchemaAdapterError):
            to_api_schema(inp)

    def test_raises_on_external_ref(self):
        with pytest.raises(SchemaAdapterError):
            to_api_schema({"$ref": "https://example.com/schema.json"})

    def test_idempotent(self):
        inp = {"$schema": "x", "type": "object",
               "properties": {"x": {"type": "array", "uniqueItems": True, "items": {"type": "string"}}}}
        once = to_api_schema(inp)
        twice = to_api_schema(once)
        assert once == twice

    def test_does_not_mutate_input(self):
        inp = {"$schema": "x", "$id": "y", "type": "object", "uniqueItems": True,
               "properties": {"z": {"$ref": "#/definitions/Z"}},
               "definitions": {"Z": {"type": "integer"}}}
        snapshot = copy.deepcopy(inp)
        _ = to_api_schema(inp)
        assert inp == snapshot

    def test_preserves_enum_required_type_properties_items(self):
        inp = {
            "type": "object",
            "required": ["a", "b"],
            "properties": {
                "a": {"type": "string", "enum": ["x", "y"]},
                "b": {"type": "array", "items": {"type": "integer"}},
                "c": {"const": "fixed"},
            },
        }
        out = to_api_schema(inp)
        assert out["type"] == "object"
        assert out["required"] == ["a", "b"]
        assert out["properties"]["a"] == {"type": "string", "enum": ["x", "y"]}
        assert out["properties"]["b"] == {"type": "array", "items": {"type": "integer"}}
        assert out["properties"]["c"] == {"const": "fixed"}

    def test_preserves_description_format_pattern(self):
        inp = {"type": "string", "description": "ISO-8601", "format": "date-time", "pattern": "^[0-9]+$"}
        out = to_api_schema(inp)
        assert out == inp  # nothing to strip

    def test_ref_siblings_conservative_behavior(self):
        """Draft 2020-12 allows $ref + siblings. Adapter drops $ref, keeps siblings."""
        inp = {"$ref": "#/definitions/Foo", "description": "sibling desc"}
        out = to_api_schema(inp)
        assert "$ref" not in out
        assert out == {"description": "sibling desc"}

    def test_real_video_analysis_schema_round_trip(self):
        """End-to-end: Plan 01's real schema -> adapter -> API-safe dict."""
        schema_path = PROJECT_ROOT / "schemas" / "artifacts" / "video_analysis.schema.json"
        canonical = json.load(open(schema_path))
        api_schema = to_api_schema(canonical)

        serialized = json.dumps(api_schema)
        assert "$schema" not in api_schema
        assert "$id" not in api_schema
        assert '"$ref"' not in serialized
        assert '"uniqueItems"' not in serialized

        # Verify the confidence map's additionalProperties (schema dict form) is preserved.
        ep = api_schema["properties"]["editing_pacing"]
        conf = ep["properties"]["confidence"]
        assert "additionalProperties" in conf
        assert conf["additionalProperties"] == {"type": "string", "enum": ["low", "medium", "high"]}

        # Verify structural keywords preserved
        assert set(api_schema["required"]) >= {"editing_pacing", "audio", "visual_style", "narrative"}
        assert api_schema["properties"]["editing_pacing"]["properties"]["pacing_style"]["enum"] == [
            "slow_contemplative", "steady_educational", "dynamic_social", "rapid_fire", "variable",
        ]
